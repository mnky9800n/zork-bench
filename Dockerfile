# Stage 1: pull game files from betamike/z-docker
FROM betamike/z-docker AS game-source

# Stage 2: minimal runtime image with dfrotz
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends frotz \
    && rm -rf /var/lib/apt/lists/*

ENV TERM=xterm

RUN mkdir -p /home/frotz/DATA

COPY --from=game-source /home/frotz/ /home/frotz/DATA/

ENTRYPOINT ["/usr/games/dfrotz"]
CMD ["/home/frotz/DATA/zork1-r88-s840726.z3"]
