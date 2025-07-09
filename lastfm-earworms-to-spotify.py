import os
import csv
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict
import pylast
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import sys

# === CONFIGURATION ===

load_dotenv()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME")
LASTFM_PASSWORD = os.getenv("LASTFM_PASSWORD")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

ALTERNATIVE_TITLES_FILE = "alternative_titles.csv"
CSV_FILE = "lastfm_scrobbles.csv"
MIN_REPEATS = 6

WEIGHTS = {
    "consecutive": 10,
    "week": 5,
    "month": 3,
    "year": 1,
}

MIN_COUNT_WEEK=30
MIN_COUNT_MONTH=50
MIN_COUNT_YEAR=200

LIMITS = {
    "repeats": 200,
    "week": 200,
    "month": 200,
    "year": 200,
    "total": 200
}

# === AUTHENTICATION ===

network = pylast.LastFMNetwork(
    api_key=LASTFM_API_KEY,
    api_secret=LASTFM_API_SECRET,
    username=LASTFM_USERNAME,
    password_hash=pylast.md5(LASTFM_PASSWORD)
)

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="playlist-modify-public"
))


# === UTILITY FUNCTIONS ===

def save_scrobbles_to_csv(scrobbles, filename):
    with open(filename, mode='w', encoding='utf-8', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['timestamp', 'artist', 'title'],
                                delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL, escapechar='\\')
        writer.writeheader()
        for s in scrobbles:
            writer.writerow({
                'timestamp': s.timestamp,
                'artist': s.track.artist.name if s.track.artist else '',
                'title': s.track.title if s.track.title else '',
            })


def load_scrobbles_from_csv(filename):
    scrobbles = []
    with open(filename, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"', escapechar='\\')
        for row in reader:
            scrobbles.append({
                'artist': row['artist'],
                'title': row['title'],
                'timestamp': int(row['timestamp'])
            })
    return scrobbles


def fetch_all_scrobbles(user):
    scrobbles = []
    recent_tracks = network.get_user(user).get_recent_tracks(limit=None)
    for scrobble in recent_tracks:
        scrobbles.append(scrobble)
    return scrobbles


def find_high_frequency_songs(scrobbles, min_count, days):
    track_timestamps = defaultdict(list)
    for s in scrobbles:
        track = (s['artist'], s['title'])
        track_timestamps[track].append(int(s['timestamp']))

    result = []
    window_seconds = days * 86400

    for track, timestamps in track_timestamps.items():
        timestamps.sort()
        n = len(timestamps)
        max_in_window = 0
        start = 0

        for end in range(n):
            while timestamps[end] - timestamps[start] > window_seconds:
                start += 1
            count_in_window = end - start + 1
            max_in_window = max(max_in_window, count_in_window)

        if max_in_window > min_count:
            result.append((track, max_in_window))

    return sorted(result, key=lambda x: x[1], reverse=True)


def find_consecutive_repeats(scrobbles, min_repeats=3):
    repeat_counts = {}
    count = 1
    prev_track = None

    for s in scrobbles:
        track = (s['artist'], s['title'])
        if track == prev_track:
            count += 1
        else:
            if prev_track and count >= min_repeats:
                repeat_counts[prev_track] = max(repeat_counts.get(prev_track, 0), count)
            count = 1
        prev_track = track

    if prev_track and count >= min_repeats:
        repeat_counts[prev_track] = max(repeat_counts.get(prev_track, 0), count)

    return sorted(repeat_counts.items(), key=lambda x: x[1], reverse=True)

def search_tracks_on_spotify(track_tuples):
    """
    Searches Spotify for given track tuples (artist, title).
    Uses alternative titles file to skip manual re-entry if available.
    """
    uris = []
    alternatives = load_alternative_titles(ALTERNATIVE_TITLES_FILE)

    for artist, title in track_tuples:
        original_key = (artist, title)

        # Use stored alternative if exists
        if original_key in alternatives:
            artist, title = alternatives[original_key]
            print(f"Using stored alternative for {original_key}: {artist} - {title}")

        while True:
            query = f"track:{title} artist:{artist}"
            results = sp.search(q=query, type='track', limit=1)
            items = results['tracks']['items']
            if items:
                uris.append(items[0]['uri'])
                #print(f"Found: {artist} - {title}")

                # If this was a new alternative, save it
                if original_key != (artist, title):
                    save_alternative_title(
                        ALTERNATIVE_TITLES_FILE,
                        original_key[0], original_key[1],
                        artist, title
                    )
                break

            else:
                print(f"Not found on Spotify: `{artist}` - `{title}`")
                try:
                    user_input = input(
                        f"Provide alternative as 'artist,title' or press ENTER to keep current. "
                        f"Press Ctrl+C to skip.\n[Current: {artist}, {title}]: "
                    )
                except KeyboardInterrupt:
                    print("\nSkipped this track.\n")
                    break

                user_input = user_input.strip()
                if user_input == "":
                    print("Keeping current artist and title. Searching again...\n")
                    time.sleep(0.2)
                    continue
                else:
                    parts = user_input.split(",")
                    if len(parts) == 2:
                        artist, title = parts[0].strip(), parts[1].strip()
                    else:
                        print("Invalid format. Provide as: artist,title or Ctrl+C to skip.")
            time.sleep(0.2)  # Avoid rate limiting

    return uris


def create_playlist_with_tracks(playlist_name, uris):
    user_id = sp.current_user()['id']
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name)
    for i in range(0, len(uris), 50):
        sp.playlist_add_items(playlist_id=playlist['id'], items=uris[i:i + 50])
    print(f"Created playlist '{playlist_name}' with {len(uris)} tracks.")

def load_alternative_titles(filename):
    alternatives = {}
    if os.path.exists(filename):
        with open(filename, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                key = (row['original_artist'], row['original_title'])
                value = (row['new_artist'], row['new_title'])
                alternatives[key] = value
    return alternatives

def save_alternative_title(filename, original_artist, original_title, new_artist, new_title):
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', encoding='utf-8', newline='') as csvfile:
        fieldnames = ['original_artist', 'original_title', 'new_artist', 'new_title']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'original_artist': original_artist,
            'original_title': original_title,
            'new_artist': new_artist,
            'new_title': new_title
        })


# === MAIN COMBINED FUNCTION ===

def combine_and_create_weighted_playlist(scrobbles):
    weighted_tracks = []

    # 1. Consecutive repeats
    repeats = find_consecutive_repeats(scrobbles, min_repeats=MIN_REPEATS)[:LIMITS["repeats"]]
    for (artist, title), max_consec in repeats:
        weight = max_consec * WEIGHTS["consecutive"]
        reason = f"played {max_consec} times in a row, weight {weight}"
        weighted_tracks.append({"artist": artist, "title": title, "weight": weight, "reason": reason})

    # 2. Weekly high frequency
    week_tracks = find_high_frequency_songs(scrobbles, min_count=MIN_COUNT_WEEK, days=7)[:LIMITS["week"]]
    for (artist, title), count in week_tracks:
        weight = count * WEIGHTS["week"]
        reason = f"played {count} times in a week, weight {weight}"
        weighted_tracks.append({"artist": artist, "title": title, "weight": weight, "reason": reason})

    # 3. Monthly high frequency
    month_tracks = find_high_frequency_songs(scrobbles, min_count=MIN_COUNT_MONTH, days=30)[:LIMITS["month"]]
    for (artist, title), count in month_tracks:
        weight = count * WEIGHTS["month"]
        reason = f"played {count} times in a month, weight {weight}"
        weighted_tracks.append({"artist": artist, "title": title, "weight": weight, "reason": reason})

    # 4. Yearly high frequency
    year_tracks = find_high_frequency_songs(scrobbles, min_count=MIN_COUNT_YEAR, days=365)[:LIMITS["year"]]
    for (artist, title), count in year_tracks:
        weight = count * WEIGHTS["year"]
        reason = f"played {count} times in a year, weight {weight}"
        weighted_tracks.append({"artist": artist, "title": title, "weight": weight, "reason": reason})

    # Deduplicate by (artist, title), keeping highest weight
    deduped_tracks = {}
    for track in weighted_tracks:
        key = (track["artist"], track["title"])
        if key not in deduped_tracks or track["weight"] > deduped_tracks[key]["weight"]:
            deduped_tracks[key] = track

    # Convert back to list and sort by weight
    final_tracks = sorted(deduped_tracks.values(), key=lambda x: x["weight"], reverse=True)
    final_tracks = final_tracks[:LIMITS["total"]]

    # Log decisions
    print(f"Creating playlist with the following {len(final_tracks)} unique tracks (sorted by weight):")
    for idx, track in enumerate(final_tracks, start=1):
        print(f"{idx:3d}. {track['artist']} - {track['title']}: {track['reason']}")

    # Search and create playlist
    uris = search_tracks_on_spotify([(t['artist'], t['title']) for t in final_tracks])
    create_playlist_with_tracks("Last.fm Weighted Combined", uris)

# === MAIN ===

if __name__ == "__main__":
    if os.path.exists(CSV_FILE):
        print(f"Loading scrobbles from {CSV_FILE} ...")
        scrobbles = load_scrobbles_from_csv(CSV_FILE)
    else:
        print("Fetching scrobbles from Last.fm...")
        fetched = fetch_all_scrobbles(LASTFM_USERNAME)
        save_scrobbles_to_csv(fetched, CSV_FILE)
        scrobbles = load_scrobbles_from_csv(CSV_FILE)

    combine_and_create_weighted_playlist(scrobbles)

