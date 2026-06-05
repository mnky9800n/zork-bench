# Stage 1: pull game files from betamike/z-docker
FROM betamike/z-docker AS game-source

# Stage 2: build bocfel (Z-machine VM) linked against remglk (the JSON Glk I/O layer).
#
# The harness talks to the game over RemGlk's structured JSON protocol instead of
# screen-scraping a terminal. RemGlk is only an I/O layer, so it is compiled into a
# VM: bocfel, the Z-machine interpreter used by Gargoyle. bocfel runs every game in
# the GAMES dict (all .z3/.z4/.z5/.z6).
FROM debian:bookworm-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# remglk: JSON implementation of the Glk API. `make` produces libremglk.a and
# Make.remglk (the link snippet bocfel includes). Pinned to a release tag.
RUN git clone https://github.com/erkyrath/remglk.git \
    && cd remglk \
    && git checkout remglk-0.3.2 \
    && make

# bocfel: its Makefile expects the Glk library in a subdirectory whose name matches
# the GLK variable (and containing Make.<name>), so the built remglk is placed at
# bocfel-2.5/remglk and `make GLK=remglk` links against it. PLATFORM=unix is the
# config.mk default but is set explicitly for clarity. Output: ./bocfel.
RUN curl -sSL https://cspiegel.github.io/bocfel/downloads/bocfel-2.5.tar.gz | tar xz \
    && cp -r remglk bocfel-2.5/remglk \
    && cd bocfel-2.5 \
    && make GLK=remglk PLATFORM=unix

# Stage 3: minimal runtime image with just the bocfel binary and the game ROMs.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /build/bocfel-2.5/bocfel /usr/local/bin/bocfel

RUN mkdir -p /home/frotz/DATA
COPY --from=game-source /home/frotz/ /home/frotz/DATA/

# bocfel speaks RemGlk JSON on stdin/stdout; it takes the game file as its argument,
# the same call shape dfrotz used (so ZorkSession's docker invocation is unchanged).
ENTRYPOINT ["/usr/local/bin/bocfel"]
CMD ["/home/frotz/DATA/zork1-r88-s840726.z3"]
