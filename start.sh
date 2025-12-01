#!/usr/bin/env bash
# start.sh -- start the bot locally (make sure env vars set)
export APCA_API_KEY_1=${APCA_API_KEY_1:-""}
export APCA_API_SECRET_1=${APCA_API_SECRET_1:-""}
export APCA_BASE_URL_1=${APCA_BASE_URL_1:-""}
python bot.py
