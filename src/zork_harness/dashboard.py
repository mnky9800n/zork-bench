"""
Zork Bench Dashboard — visualizes playthrough data from JSONL session logs.

Run with:
    zork-dashboard
    zork-dashboard --session-dir /path/to/sessions
    zork-dashboard --port 8051
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import dash
from dash import Input, Output, State, callback, dcc, html
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

ZORK1_MAX_SCORE = 350
ZORK1_TOTAL_ROOMS = 40
TOOL_NAMES = {"record_room", "look_up_room", "list_known_rooms", "find_path", "add_note"}
MAP_TOOL_NAMES = {"record_room", "look_up_room", "list_known_rooms", "find_path"}


@dataclass
class TurnRecord:
    turn: int
    command: str
    output: str
    tool_calls: list[dict]
    room: Optional[str]
    died: bool
    score: Optional[int]
    timestamp: Optional[datetime]


@dataclass
class Session:
    session_id: str          # filename stem
    path: Path
    game: str
    model: str
    backend: str
    map_mode: str
    player_type: str
    started_at: Optional[datetime]

    turns: list[TurnRecord] = field(default_factory=list)

    # summary — computed from turns if not present in file
    total_turns: int = 0
    deaths: int = 0
    death_turns: list[int] = field(default_factory=list)
    unique_rooms: int = 0
    rooms_list: list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    room_sequence: list[dict] = field(default_factory=list)

    has_summary: bool = False

    @property
    def final_score(self) -> Optional[int]:
        for t in reversed(self.turns):
            if t.score is not None:
                return t.score
        return None

    @property
    def total_tool_calls(self) -> int:
        return sum(len(t.tool_calls) for t in self.turns)

    @property
    def map_tool_calls(self) -> int:
        count = 0
        for t in self.turns:
            for tc in t.tool_calls:
                if tc.get("name") in MAP_TOOL_NAMES:
                    count += 1
        return count

    @property
    def turns_to_first_death(self) -> Optional[int]:
        return self.death_turns[0] if self.death_turns else None

    @property
    def turns_to_first_score(self) -> Optional[int]:
        """Turn number when the score first increases above zero."""
        for t in self.turns:
            if t.score is not None and t.score > 0:
                return t.turn
        return None

    def tool_call_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.turns:
            for tc in t.tool_calls:
                name = tc.get("name", "unknown")
                counts[name] = counts.get(name, 0) + 1
        return counts

    def score_over_turns(self) -> tuple[list[int], list[Optional[int]]]:
        """Returns (turn_numbers, scores) for all turns that have a score."""
        turns, scores = [], []
        last_score = None
        for t in self.turns:
            if t.score is not None:
                last_score = t.score
            turns.append(t.turn)
            scores.append(last_score)
        return turns, scores

    def cumulative_rooms_over_turns(self) -> tuple[list[int], list[int]]:
        """Returns (turn_numbers, cumulative_unique_rooms) for all turns."""
        seen: set[str] = set()
        turns, counts = [], []
        for t in self.turns:
            if t.room and t.room not in seen:
                seen.add(t.room)
            turns.append(t.turn)
            counts.append(len(seen))
        return turns, counts

    def inter_turn_seconds(self) -> tuple[list[int], list[float]]:
        """Returns (turn_number, seconds_since_previous_turn) for human sessions."""
        result_turns, result_deltas = [], []
        prev: Optional[datetime] = None
        for t in self.turns:
            if t.timestamp is not None:
                if prev is not None:
                    delta = (t.timestamp - prev).total_seconds()
                    result_turns.append(t.turn)
                    result_deltas.append(delta)
                prev = t.timestamp
        return result_turns, result_deltas


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S.%f+00:00", "%Y-%m-%dT%H:%M:%S+00:00"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def parse_session(path: Path) -> Optional[Session]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None

    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return None

    header = records[0]
    if header.get("type") != "header":
        return None

    session = Session(
        session_id=path.stem,
        path=path,
        game=header.get("game", "unknown"),
        model=header.get("model", "unknown"),
        backend=header.get("backend", "unknown"),
        map_mode=header.get("map_mode", ""),
        player_type=header.get("player_type", "unknown"),
        started_at=_parse_timestamp(header.get("started_at")),
    )

    summary_record = None
    for record in records[1:]:
        rtype = record.get("type")
        if rtype == "turn":
            ts = _parse_timestamp(record.get("timestamp"))
            session.turns.append(TurnRecord(
                turn=record.get("turn", 0),
                command=record.get("command", ""),
                output=record.get("output", ""),
                tool_calls=record.get("tool_calls") or [],
                room=record.get("room"),
                died=record.get("died", False),
                score=record.get("score"),
                timestamp=ts,
            ))
        elif rtype == "summary":
            summary_record = record

    if summary_record:
        session.has_summary = True
        session.total_turns = summary_record.get("total_turns", len(session.turns))
        session.deaths = summary_record.get("deaths", 0)
        session.death_turns = summary_record.get("death_turns") or []
        session.unique_rooms = summary_record.get("unique_rooms", 0)
        session.rooms_list = summary_record.get("rooms_list") or []
        session.total_input_tokens = summary_record.get("total_input_tokens", 0)
        session.total_output_tokens = summary_record.get("total_output_tokens", 0)
        session.room_sequence = summary_record.get("room_sequence") or []
    else:
        # Compute from turn data
        session.total_turns = len(session.turns)
        session.death_turns = [t.turn for t in session.turns if t.died]
        session.deaths = len(session.death_turns)
        seen_rooms: list[str] = []
        for t in session.turns:
            if t.room and t.room not in seen_rooms:
                seen_rooms.append(t.room)
        session.rooms_list = seen_rooms
        session.unique_rooms = len(seen_rooms)
        session.room_sequence = [
            {"turn": t.turn, "room": t.room}
            for t in session.turns
            if t.room
        ]

    return session


def load_sessions(session_dir: Path) -> list[Session]:
    sessions = []
    for path in sorted(session_dir.glob("*.jsonl")):
        try:
            s = parse_session(path)
            if s is not None:
                sessions.append(s)
        except Exception as exc:
            print(f"Warning: failed to parse {path.name}: {exc}")
    return sessions


# ---------------------------------------------------------------------------
# Colour palette — dark terminal aesthetic
# ---------------------------------------------------------------------------

DARK_BG = "#0d0d0d"
PANEL_BG = "#141414"
BORDER = "#2a2a2a"
TEXT_PRIMARY = "#e8e8e8"
TEXT_MUTED = "#6b7280"
ACCENT_GREEN = "#00ff41"   # classic terminal green
ACCENT_AMBER = "#ffb347"
ACCENT_BLUE = "#4fc3f7"
ACCENT_RED = "#ff6b6b"
ACCENT_PURPLE = "#ce93d8"

PLOTLY_TEMPLATE = dict(
    layout=dict(
        paper_bgcolor=PANEL_BG,
        plot_bgcolor=PANEL_BG,
        font=dict(color=TEXT_PRIMARY, family="'Courier New', monospace"),
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER),
        legend=dict(bgcolor=PANEL_BG, bordercolor=BORDER, borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40),
    )
)

MODEL_COLORS = [ACCENT_GREEN, ACCENT_BLUE, ACCENT_AMBER, ACCENT_PURPLE, ACCENT_RED, "#80cbc4", "#f48fb1"]


def _chart_layout(**kwargs) -> dict:
    base = dict(PLOTLY_TEMPLATE["layout"])
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _card(children, style: Optional[dict] = None) -> html.Div:
    base = {
        "background": PANEL_BG,
        "border": f"1px solid {BORDER}",
        "borderRadius": "4px",
        "padding": "16px",
        "marginBottom": "16px",
    }
    if style:
        base.update(style)
    return html.Div(children, style=base)


def _section_title(text: str) -> html.H3:
    return html.H3(text, style={
        "color": ACCENT_GREEN,
        "fontFamily": "'Courier New', monospace",
        "fontSize": "14px",
        "textTransform": "uppercase",
        "letterSpacing": "2px",
        "marginTop": "0",
        "marginBottom": "12px",
        "borderBottom": f"1px solid {BORDER}",
        "paddingBottom": "8px",
    })


def _stat_box(label: str, value: str) -> html.Div:
    return html.Div([
        html.Div(value, style={
            "color": ACCENT_GREEN,
            "fontFamily": "'Courier New', monospace",
            "fontSize": "24px",
            "fontWeight": "bold",
        }),
        html.Div(label, style={
            "color": TEXT_MUTED,
            "fontFamily": "'Courier New', monospace",
            "fontSize": "11px",
            "textTransform": "uppercase",
            "letterSpacing": "1px",
        }),
    ], style={
        "textAlign": "center",
        "padding": "12px 16px",
        "background": DARK_BG,
        "border": f"1px solid {BORDER}",
        "borderRadius": "4px",
        "minWidth": "100px",
    })


# ---------------------------------------------------------------------------
# Overview table
# ---------------------------------------------------------------------------

def _build_overview_table(sessions: list[Session]) -> html.Table:
    headers = [
        "Session", "Model", "Backend", "Map Mode",
        "Turns", "Unique Rooms", "Deaths", "Final Score", "Tokens In", "Tokens Out",
    ]

    header_cells = [
        html.Th(h, style={
            "color": ACCENT_GREEN,
            "fontFamily": "'Courier New', monospace",
            "fontSize": "11px",
            "textTransform": "uppercase",
            "letterSpacing": "1px",
            "padding": "8px 12px",
            "borderBottom": f"1px solid {BORDER}",
            "whiteSpace": "nowrap",
            "cursor": "default",
        })
        for h in headers
    ]

    rows = []
    for s in sessions:
        started = s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else s.session_id
        final_score = s.final_score
        score_str = str(final_score) if final_score is not None else "—"
        tokens_in = str(s.total_input_tokens) if s.total_input_tokens else "—"
        tokens_out = str(s.total_output_tokens) if s.total_output_tokens else "—"

        cells = [
            html.Td(
                html.A(started, href="#", id={"type": "session-link", "index": s.session_id},
                       style={"color": ACCENT_BLUE, "textDecoration": "none", "cursor": "pointer"}),
                style={"padding": "7px 12px", "whiteSpace": "nowrap"}
            ),
            html.Td(s.model, style={"padding": "7px 12px", "color": ACCENT_AMBER, "whiteSpace": "nowrap"}),
            html.Td(s.backend, style={"padding": "7px 12px"}),
            html.Td(s.map_mode or "—", style={"padding": "7px 12px"}),
            html.Td(str(s.total_turns), style={"padding": "7px 12px", "textAlign": "right"}),
            html.Td(str(s.unique_rooms), style={"padding": "7px 12px", "textAlign": "right"}),
            html.Td(str(s.deaths), style={
                "padding": "7px 12px",
                "textAlign": "right",
                "color": ACCENT_RED if s.deaths > 0 else TEXT_PRIMARY,
            }),
            html.Td(score_str, style={"padding": "7px 12px", "textAlign": "right"}),
            html.Td(tokens_in, style={"padding": "7px 12px", "textAlign": "right"}),
            html.Td(tokens_out, style={"padding": "7px 12px", "textAlign": "right"}),
        ]

        row_style = {
            "borderBottom": f"1px solid {BORDER}",
            "fontFamily": "'Courier New', monospace",
            "fontSize": "13px",
            "color": TEXT_PRIMARY,
        }
        rows.append(html.Tr(cells, style=row_style, id={"type": "session-row", "index": s.session_id}))

    return html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )


# ---------------------------------------------------------------------------
# Session detail view
# ---------------------------------------------------------------------------

def _build_score_chart(session: Session) -> go.Figure:
    turns, scores = session.score_over_turns()
    # Filter to only turns where we have score data to show
    filtered_turns = [t for t, s in zip(turns, scores) if s is not None]
    filtered_scores = [s for s in scores if s is not None]

    if not filtered_scores:
        fig = go.Figure(layout=_chart_layout(title="Score Progression (no score data)"))
        return fig

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=filtered_turns, y=filtered_scores,
        mode="lines+markers",
        line=dict(color=ACCENT_GREEN, width=2),
        marker=dict(size=6, color=ACCENT_GREEN),
        name="Score",
        hovertemplate="Turn %{x}: %{y} pts<extra></extra>",
    ))
    fig.add_hline(y=ZORK1_MAX_SCORE, line_dash="dot", line_color=BORDER,
                  annotation_text="Max (350)", annotation_font_color=TEXT_MUTED)
    for death_turn in session.death_turns:
        fig.add_vline(x=death_turn, line_dash="dash", line_color=ACCENT_RED, line_width=1,
                      annotation_text="☠", annotation_font_color=ACCENT_RED)
    fig.update_layout(**_chart_layout(
        title="Score Over Turns",
        xaxis_title="Turn",
        yaxis_title="Score",
        yaxis_range=[0, ZORK1_MAX_SCORE + 10],
    ))
    return fig


def _build_rooms_chart(session: Session) -> go.Figure:
    turns, counts = session.cumulative_rooms_over_turns()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=turns, y=counts,
        mode="lines",
        line=dict(color=ACCENT_BLUE, width=2),
        fill="tozeroy",
        fillcolor=f"rgba(79,195,247,0.08)",
        name="Rooms Discovered",
        hovertemplate="Turn %{x}: %{y} rooms<extra></extra>",
    ))
    fig.add_hline(y=ZORK1_TOTAL_ROOMS, line_dash="dot", line_color=BORDER,
                  annotation_text="Total Rooms (40)", annotation_font_color=TEXT_MUTED)
    fig.update_layout(**_chart_layout(
        title="Room Discovery Over Turns",
        xaxis_title="Turn",
        yaxis_title="Unique Rooms",
        yaxis_range=[0, ZORK1_TOTAL_ROOMS + 2],
    ))
    return fig


def _build_tool_chart(session: Session) -> go.Figure:
    counts = session.tool_call_counts()
    if not counts:
        fig = go.Figure(layout=_chart_layout(title="Tool Usage (no tool calls)"))
        return fig

    labels = list(counts.keys())
    values = list(counts.values())
    colors = [ACCENT_GREEN if l in MAP_TOOL_NAMES else ACCENT_AMBER for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors, line=dict(color=DARK_BG, width=2)),
        textfont=dict(family="'Courier New', monospace", color=TEXT_PRIMARY),
        hovertemplate="%{label}: %{value} calls<extra></extra>",
    ))
    fig.update_layout(**_chart_layout(title="Tool Call Distribution"))
    return fig


def _build_inter_turn_chart(session: Session) -> go.Figure:
    turns, deltas = session.inter_turn_seconds()
    if not deltas:
        fig = go.Figure(layout=_chart_layout(title="Time Between Turns (no timestamp data)"))
        return fig

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=turns, y=deltas,
        marker_color=ACCENT_AMBER,
        hovertemplate="Turn %{x}: %{y:.1f}s<extra></extra>",
        name="Seconds",
    ))
    fig.update_layout(**_chart_layout(
        title="Time Between Turns (seconds)",
        xaxis_title="Turn",
        yaxis_title="Seconds",
    ))
    return fig


def _build_transcript(session: Session) -> html.Div:
    items = []
    for t in session.turns:
        cmd_color = ACCENT_GREEN
        if t.died:
            cmd_color = ACCENT_RED

        turn_elements = [
            html.Div([
                html.Span(f"[{t.turn:03d}] ", style={"color": TEXT_MUTED}),
                html.Span("> ", style={"color": ACCENT_GREEN}),
                html.Span(t.command, style={"color": cmd_color}),
            ], style={"marginBottom": "4px"}),
        ]

        if t.output:
            turn_elements.append(html.Pre(
                t.output,
                style={
                    "color": TEXT_PRIMARY,
                    "margin": "0 0 6px 24px",
                    "whiteSpace": "pre-wrap",
                    "fontSize": "12px",
                    "lineHeight": "1.5",
                }
            ))

        for tc in t.tool_calls:
            name = tc.get("name", "?")
            inp = tc.get("input", {})
            result = tc.get("result", "")
            inp_str = json.dumps(inp, ensure_ascii=False) if inp else ""
            turn_elements.append(html.Div([
                html.Span("  TOOL ", style={"color": ACCENT_PURPLE, "fontSize": "11px"}),
                html.Span(name, style={"color": ACCENT_BLUE, "fontWeight": "bold"}),
                html.Span(f"({inp_str})", style={"color": TEXT_MUTED, "fontSize": "11px"}),
                html.Br(),
                html.Span(f"    => {result}", style={"color": TEXT_MUTED, "fontSize": "11px"}),
            ], style={"marginBottom": "6px", "marginLeft": "24px"}))

        if t.died:
            turn_elements.append(html.Div("  *** YOU DIED ***", style={
                "color": ACCENT_RED, "fontWeight": "bold", "marginBottom": "6px",
            }))

        border_color = ACCENT_RED if t.died else BORDER
        items.append(html.Div(turn_elements, style={
            "borderLeft": f"2px solid {border_color}",
            "paddingLeft": "12px",
            "marginBottom": "16px",
            "fontFamily": "'Courier New', monospace",
            "fontSize": "13px",
        }))

    if not items:
        return html.Div("No turns recorded.", style={"color": TEXT_MUTED, "fontFamily": "'Courier New', monospace"})

    return html.Div(items, style={
        "maxHeight": "600px",
        "overflowY": "auto",
        "padding": "8px",
        "background": DARK_BG,
        "border": f"1px solid {BORDER}",
        "borderRadius": "4px",
    })


def _build_session_detail(session: Session) -> html.Div:
    final_score = session.final_score
    score_str = str(final_score) if final_score is not None else "—"
    pct_score = f"{final_score / ZORK1_MAX_SCORE * 100:.0f}%" if final_score else "—"
    pct_rooms = f"{session.unique_rooms / ZORK1_TOTAL_ROOMS * 100:.0f}%"
    tool_eff = (
        f"{session.map_tool_calls / session.total_turns:.2f}/turn"
        if session.total_turns else "—"
    )

    started_str = session.started_at.strftime("%Y-%m-%d %H:%M UTC") if session.started_at else "—"

    stats_row = html.Div([
        _stat_box("Model", session.model),
        _stat_box("Backend", session.backend),
        _stat_box("Map Mode", session.map_mode or "—"),
        _stat_box("Turns", str(session.total_turns)),
        _stat_box("Score", f"{score_str} / 350"),
        _stat_box("Score %", pct_score),
        _stat_box("Rooms", f"{session.unique_rooms} / 40"),
        _stat_box("Room %", pct_rooms),
        _stat_box("Deaths", str(session.deaths)),
        _stat_box("Map Tools", str(session.map_tool_calls)),
        _stat_box("Tool Eff.", tool_eff),
    ], style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginBottom": "16px"})

    charts_row = html.Div([
        html.Div(dcc.Graph(figure=_build_score_chart(session), config={"displayModeBar": False}),
                 style={"flex": "1", "minWidth": "340px"}),
        html.Div(dcc.Graph(figure=_build_rooms_chart(session), config={"displayModeBar": False}),
                 style={"flex": "1", "minWidth": "340px"}),
    ], style={"display": "flex", "flexWrap": "wrap", "gap": "16px"})

    has_tool_calls = bool(session.tool_call_counts())
    is_human = session.player_type == "human"

    tool_and_timing_row = html.Div([
        html.Div(
            dcc.Graph(figure=_build_tool_chart(session), config={"displayModeBar": False}),
            style={"flex": "1", "minWidth": "280px"},
        ) if has_tool_calls else html.Div(),
        html.Div(
            dcc.Graph(figure=_build_inter_turn_chart(session), config={"displayModeBar": False}),
            style={"flex": "1", "minWidth": "280px"},
        ) if is_human else html.Div(),
    ], style={"display": "flex", "flexWrap": "wrap", "gap": "16px"})

    return html.Div([
        html.Div([
            html.Button("← Back to overview", id="back-button", n_clicks=0, style={
                "background": "none",
                "border": f"1px solid {BORDER}",
                "color": ACCENT_BLUE,
                "fontFamily": "'Courier New', monospace",
                "fontSize": "13px",
                "cursor": "pointer",
                "padding": "6px 12px",
                "borderRadius": "4px",
                "marginBottom": "16px",
            }),
            html.H2(f"Session: {started_str}", style={
                "color": TEXT_PRIMARY,
                "fontFamily": "'Courier New', monospace",
                "fontSize": "16px",
                "margin": "0 0 4px 0",
            }),
            html.Div(f"Game: {session.game}  |  Player type: {session.player_type}  |  {'Summary present' if session.has_summary else 'No summary — stats computed from turns'}",
                     style={"color": TEXT_MUTED, "fontFamily": "'Courier New', monospace", "fontSize": "11px", "marginBottom": "16px"}),
        ]),
        stats_row,
        _card([_section_title("Score & Room Discovery"), charts_row]),
        _card([_section_title("Tool Usage & Turn Timing"), tool_and_timing_row]) if (has_tool_calls or is_human) else html.Div(),
        _card([_section_title("Turn-by-Turn Transcript"), _build_transcript(session)]),
    ])


# ---------------------------------------------------------------------------
# Cross-session comparison
# ---------------------------------------------------------------------------

def _build_comparison(sessions: list[Session]) -> html.Div:
    if len(sessions) < 2:
        return html.Div("Add more sessions to enable cross-session comparison.",
                        style={"color": TEXT_MUTED, "fontFamily": "'Courier New', monospace", "padding": "16px"})

    model_color_map: dict[str, str] = {}
    models = sorted({s.model for s in sessions})
    for i, m in enumerate(models):
        model_color_map[m] = MODEL_COLORS[i % len(MODEL_COLORS)]

    labels = [s.started_at.strftime("%m-%d %H:%M") if s.started_at else s.session_id for s in sessions]

    # --- Rooms bar chart ---
    rooms_fig = go.Figure()
    for s, label in zip(sessions, labels):
        rooms_fig.add_trace(go.Bar(
            name=label,
            x=[label],
            y=[s.unique_rooms],
            marker_color=model_color_map.get(s.model, ACCENT_BLUE),
            hovertemplate=f"{label} ({s.model}): %{{y}} rooms<extra></extra>",
        ))
    rooms_fig.add_hline(y=ZORK1_TOTAL_ROOMS, line_dash="dot", line_color=BORDER,
                        annotation_text="Total (40)", annotation_font_color=TEXT_MUTED)
    rooms_fig.update_layout(**_chart_layout(
        title="Rooms Discovered per Session",
        xaxis_title="Session",
        yaxis_title="Unique Rooms",
        barmode="group",
        showlegend=False,
    ))

    # --- Score bar chart ---
    score_fig = go.Figure()
    for s, label in zip(sessions, labels):
        final_score = s.final_score or 0
        score_fig.add_trace(go.Bar(
            name=label,
            x=[label],
            y=[final_score],
            marker_color=model_color_map.get(s.model, ACCENT_GREEN),
            hovertemplate=f"{label} ({s.model}): %{{y}} pts<extra></extra>",
        ))
    score_fig.add_hline(y=ZORK1_MAX_SCORE, line_dash="dot", line_color=BORDER,
                        annotation_text="Max (350)", annotation_font_color=TEXT_MUTED)
    score_fig.update_layout(**_chart_layout(
        title="Final Score per Session",
        xaxis_title="Session",
        yaxis_title="Score",
        barmode="group",
        showlegend=False,
    ))

    # --- Deaths bar chart ---
    deaths_fig = go.Figure()
    deaths_fig.add_trace(go.Bar(
        x=labels,
        y=[s.deaths for s in sessions],
        marker_color=[ACCENT_RED if s.deaths > 0 else ACCENT_GREEN for s in sessions],
        hovertemplate="%{x}: %{y} deaths<extra></extra>",
        name="Deaths",
    ))
    deaths_fig.update_layout(**_chart_layout(
        title="Deaths per Session",
        xaxis_title="Session",
        yaxis_title="Deaths",
        showlegend=False,
    ))

    # --- Score trajectories overlay ---
    traj_fig = go.Figure()
    for s, label in zip(sessions, labels):
        turns, scores = s.score_over_turns()
        filtered = [(t, sc) for t, sc in zip(turns, scores) if sc is not None]
        if filtered:
            t_vals, s_vals = zip(*filtered)
            traj_fig.add_trace(go.Scatter(
                x=t_vals, y=s_vals,
                mode="lines",
                name=f"{label} ({s.model})",
                line=dict(color=model_color_map.get(s.model, ACCENT_BLUE), width=2),
                hovertemplate=f"{label}: turn %{{x}} = %{{y}} pts<extra></extra>",
            ))
    traj_fig.update_layout(**_chart_layout(
        title="Score Trajectories",
        xaxis_title="Turn",
        yaxis_title="Score",
        yaxis_range=[0, ZORK1_MAX_SCORE + 10],
    ))

    # --- Room discovery trajectories ---
    room_traj_fig = go.Figure()
    for s, label in zip(sessions, labels):
        turns, counts = s.cumulative_rooms_over_turns()
        room_traj_fig.add_trace(go.Scatter(
            x=turns, y=counts,
            mode="lines",
            name=f"{label} ({s.model})",
            line=dict(color=model_color_map.get(s.model, ACCENT_BLUE), width=2),
            hovertemplate=f"{label}: turn %{{x}} = %{{y}} rooms<extra></extra>",
        ))
    room_traj_fig.add_hline(y=ZORK1_TOTAL_ROOMS, line_dash="dot", line_color=BORDER,
                            annotation_text="Total (40)", annotation_font_color=TEXT_MUTED)
    room_traj_fig.update_layout(**_chart_layout(
        title="Room Discovery Trajectories",
        xaxis_title="Turn",
        yaxis_title="Unique Rooms",
        yaxis_range=[0, ZORK1_TOTAL_ROOMS + 2],
    ))

    chart_row1 = html.Div([
        html.Div(dcc.Graph(figure=rooms_fig, config={"displayModeBar": False}), style={"flex": "1", "minWidth": "300px"}),
        html.Div(dcc.Graph(figure=score_fig, config={"displayModeBar": False}), style={"flex": "1", "minWidth": "300px"}),
        html.Div(dcc.Graph(figure=deaths_fig, config={"displayModeBar": False}), style={"flex": "1", "minWidth": "300px"}),
    ], style={"display": "flex", "flexWrap": "wrap", "gap": "16px"})

    chart_row2 = html.Div([
        html.Div(dcc.Graph(figure=traj_fig, config={"displayModeBar": False}), style={"flex": "1", "minWidth": "400px"}),
        html.Div(dcc.Graph(figure=room_traj_fig, config={"displayModeBar": False}), style={"flex": "1", "minWidth": "400px"}),
    ], style={"display": "flex", "flexWrap": "wrap", "gap": "16px"})

    return html.Div([
        _card([_section_title("Per-Session Metrics"), chart_row1]),
        _card([_section_title("Cross-Session Trajectories"), chart_row2]),
    ])


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------

GLOBAL_SESSIONS: list[Session] = []
SESSIONS_DIR: Path = Path("sessions")


def build_app() -> dash.Dash:
    app = dash.Dash(
        __name__,
        title="Zork Bench Dashboard",
        update_title=None,
        suppress_callback_exceptions=True,
    )

    app.layout = html.Div([
        # Interval for auto-refresh scan
        dcc.Interval(id="refresh-interval", interval=30_000, n_intervals=0),
        # Store the selected session ID
        dcc.Store(id="selected-session-id", data=None),
        # Store session data as JSON (list of dicts) — refreshed on interval
        dcc.Store(id="sessions-store", data=None),

        # Header
        html.Div([
            html.H1("ZORK BENCH", style={
                "color": ACCENT_GREEN,
                "fontFamily": "'Courier New', monospace",
                "fontSize": "28px",
                "letterSpacing": "6px",
                "margin": "0",
                "textShadow": f"0 0 20px {ACCENT_GREEN}",
            }),
            html.Div("LLM Text Adventure Benchmark Dashboard", style={
                "color": TEXT_MUTED,
                "fontFamily": "'Courier New', monospace",
                "fontSize": "13px",
                "marginTop": "4px",
            }),
            html.Div(id="session-count-display", style={
                "color": TEXT_MUTED,
                "fontFamily": "'Courier New', monospace",
                "fontSize": "11px",
                "marginTop": "4px",
            }),
        ], style={
            "background": PANEL_BG,
            "borderBottom": f"1px solid {BORDER}",
            "padding": "20px 32px",
            "marginBottom": "0",
        }),

        # Tab bar
        html.Div([
            dcc.Tabs(
                id="main-tabs",
                value="overview",
                children=[
                    dcc.Tab(label="SESSION OVERVIEW", value="overview"),
                    dcc.Tab(label="SESSION DETAIL", value="detail"),
                    dcc.Tab(label="COMPARISON", value="comparison"),
                ],
                style={"fontFamily": "'Courier New', monospace"},
                colors={"border": BORDER, "primary": ACCENT_GREEN, "background": PANEL_BG},
            ),
        ], style={"background": PANEL_BG, "paddingLeft": "16px", "borderBottom": f"1px solid {BORDER}"}),

        # Main content area
        html.Div(id="page-content", style={
            "padding": "24px 32px",
            "minHeight": "calc(100vh - 140px)",
        }),

    ], style={
        "background": DARK_BG,
        "color": TEXT_PRIMARY,
        "minHeight": "100vh",
        "margin": "0",
        "padding": "0",
    })

    # -- Callbacks --

    @app.callback(
        Output("sessions-store", "data"),
        Output("session-count-display", "children"),
        Input("refresh-interval", "n_intervals"),
    )
    def refresh_sessions(n_intervals):
        sessions = load_sessions(SESSIONS_DIR)
        GLOBAL_SESSIONS.clear()
        GLOBAL_SESSIONS.extend(sessions)
        data = [s.session_id for s in sessions]
        count_str = f"{len(sessions)} session(s) loaded from {SESSIONS_DIR}"
        return data, count_str

    @app.callback(
        Output("selected-session-id", "data"),
        Output("main-tabs", "value"),
        Input({"type": "session-link", "index": dash.ALL}, "n_clicks"),
        Input("back-button", "n_clicks"),
        State({"type": "session-link", "index": dash.ALL}, "id"),
        State("selected-session-id", "data"),
        prevent_initial_call=True,
    )
    def handle_session_selection(link_clicks, back_clicks, link_ids, current_session):
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_session, "overview"

        trigger_id = ctx.triggered[0]["prop_id"]

        if "back-button" in trigger_id:
            return None, "overview"

        # Find which link was clicked
        for i, clicks in enumerate(link_clicks):
            if clicks and clicks > 0:
                session_id = link_ids[i]["index"]
                return session_id, "detail"

        return current_session, "overview"

    @app.callback(
        Output("page-content", "children"),
        Input("main-tabs", "value"),
        Input("sessions-store", "data"),
        State("selected-session-id", "data"),
    )
    def render_page(tab, sessions_data, selected_session_id):
        sessions = GLOBAL_SESSIONS

        if tab == "overview":
            if not sessions:
                return _card(html.Div(
                    f"No sessions found in {SESSIONS_DIR}. Run the harness to generate sessions.",
                    style={"color": TEXT_MUTED, "fontFamily": "'Courier New', monospace", "padding": "32px", "textAlign": "center"}
                ))
            return _card([
                _section_title(f"All Sessions ({len(sessions)})"),
                _build_overview_table(sessions),
            ])

        elif tab == "detail":
            if not selected_session_id:
                return _card(html.Div(
                    "Click a session in the overview table to view its detail.",
                    style={"color": TEXT_MUTED, "fontFamily": "'Courier New', monospace", "padding": "32px", "textAlign": "center"}
                ))
            session_map = {s.session_id: s for s in sessions}
            session = session_map.get(selected_session_id)
            if session is None:
                return _card(html.Div(
                    f"Session '{selected_session_id}' not found.",
                    style={"color": ACCENT_RED, "fontFamily": "'Courier New', monospace"}
                ))
            return _build_session_detail(session)

        elif tab == "comparison":
            return _card([
                _section_title("Cross-Session Comparison"),
                _build_comparison(sessions),
            ])

        return html.Div("Unknown tab.")

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Zork Bench Dashboard")
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=Path("sessions"),
        help="Directory containing JSONL session files (default: ./sessions)",
    )
    parser.add_argument("--port", type=int, default=8050, help="Port to serve on (default: 8050)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable Dash debug mode")
    args = parser.parse_args()

    global SESSIONS_DIR
    SESSIONS_DIR = args.session_dir.resolve()

    if not SESSIONS_DIR.exists():
        print(f"Warning: session directory '{SESSIONS_DIR}' does not exist. It will be watched once created.")
    else:
        print(f"Loading sessions from: {SESSIONS_DIR}")
        initial = load_sessions(SESSIONS_DIR)
        GLOBAL_SESSIONS.extend(initial)
        print(f"  Found {len(initial)} session(s).")

    app = build_app()
    print(f"Dashboard running at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
