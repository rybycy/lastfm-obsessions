#!/bin/bash

# === setup.sh ===
# Setup script for Last.fm -> Spotify earworm playlist generator

set -e

echo "=============================="
echo "Setting up virtual environment"
echo "=============================="

# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

echo "Virtual environment created and activated."

# 2. Install dependencies
echo "Installing dependencies from requirements.txt ..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Dependencies installed."

# 3. Check if .env exists; if not, prompt for secrets
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
  echo "=============================="
  echo ".env file already exists. Using existing configuration."
  echo "=============================="
else
  echo "=============================="
  echo "Configuring environment secrets"
  echo "=============================="

  touch $ENV_FILE

  # Helper to prompt and write env variables
  prompt_and_write_env() {
    var_name=$1
    prompt_text=$2
    url_info=$3

    echo ""
    echo "$prompt_text"
    if [ ! -z "$url_info" ]; then
      echo "See: $url_info"
    fi
    read -p "$var_name: " input
    echo "$var_name=\"$input\"" >> $ENV_FILE
  }

  prompt_and_write_env "LASTFM_API_KEY" "Enter your Last.fm API Key" "https://www.last.fm/api/account/create"
  prompt_and_write_env "LASTFM_API_SECRET" "Enter your Last.fm API Secret" "https://www.last.fm/api/account/create"
  prompt_and_write_env "LASTFM_USERNAME" "Enter your Last.fm Username"
  prompt_and_write_env "LASTFM_PASSWORD" "Enter your Last.fm Password"

  prompt_and_write_env "SPOTIFY_CLIENT_ID" "Enter your Spotify Client ID" "https://developer.spotify.com/dashboard/applications"
  prompt_and_write_env "SPOTIFY_CLIENT_SECRET" "Enter your Spotify Client Secret" "https://developer.spotify.com/dashboard/applications"
  prompt_and_write_env "SPOTIFY_REDIRECT_URI" "Enter your Spotify Redirect URI (e.g. http://localhost:8888/callback)" "https://developer.spotify.com/dashboard/applications"

  echo ""
  echo "All secrets saved to $ENV_FILE."
fi

# 4. Start the script
echo "=============================="
echo "Running your script"
echo "=============================="

python lastfm-earworms-to-spotify.py

