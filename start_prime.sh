#!/bin/bash

SESSION_NAME="gaia_net"

# Check if the session exists
tmux has-session -t $SESSION_NAME 2>/dev/null

if [ $? != 0 ]; then
  # Create a new session and name the first window
  tmux new-session -d -s $SESSION_NAME -n command_center
  
  # Trigger the Dynamic Bootloader
  tmux send-keys -t $SESSION_NAME:command_center.0 "./venv/bin/python3 ignite.py" C-m
  
  echo "Gaia Prime Environment Created."
else
  echo "Gaia Prime is already running."
fi

# Attach to the session
tmux attach -t $SESSION_NAME