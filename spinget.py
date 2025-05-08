#!/usr/bin/env python3
"""
This script captures a radio show and saves it as an mp3 file.
It fetches the stream using m3u8 and concatenates the downloaded segments.

Usage:
    python3 spinget.py MM/DD/YYYY HH:MM hours

Example:
    python3 spinget.py 11/20/2021 10:00 1
    Capture 1 hour show starting at 10:00am on November 20, 2021.

Requires ffmpeg and appropriate Python packages (m3u8, requests).

Version 2.1 by Mathias for WXOX
Version 2.2 by Mason Daugherty for WBOR
"""

import argparse
from datetime import datetime, timezone, timedelta
import os
import subprocess
import sys
from urllib.error import HTTPError

import concurrent.futures

import json
from zoneinfo import ZoneInfo
import m3u8
import requests

station_config = {}

def get_index_url(timestamp):
    return station_config["index_url_pattern"].format(shortcode=station_config["shortcode"], timestamp=timestamp)

def seg_to_file(n, seguri):
    """
    Given a segment URI, return a unique file name for the segment.

    Parameters:
    - n: The segment number.
    - seguri: The segment URI.

    Returns:
    - A file name string.
    """
    chunk_id = seguri.split("/")[-1]
    return f"{station_config['shortcode']}_{n:05d}_{chunk_id}.tmp.mpeg"


def concat(segment_list, output, rm):
    """
    Concatenate the segments in `segment_list` into a single file named `output`.
    If `rm` is set True then also delete the downloaded segments if concatenation succeeds.

    Parameters:
    - segment_list: A list of segment URIs.
    - output: The output file name.
    - rm: Whether to remove the downloaded segments after concatenation.

    Returns:
    - True on success.
    """
    print(f"Creating index file for {len(segment_list)} segments...")
    index_file = f"{output}.index"
    with open(index_file, "w", encoding="utf-8") as fdout:
        for n, seguri in enumerate(segment_list, start=1):
            file_name = seg_to_file(n, seguri)
            fdout.write(f"file {file_name}\n")

    print("Concatenating with ffmpeg...")
    # Arguments for ffmpeg:
    # -f concat: Use the concat demuxer
    # -safe 0: Allow unsafe file names
    # -i index_file: Read the list of files to concatenate from the index file
    # -c copy: Copy the streams directly without re-encoding
    # output: The output file name
    ffproc = subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            index_file,
            "-c",
            "copy",
            output,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )

    if ffproc.returncode != 0:
        print("ffmpeg run failed! Output:")
        print(ffproc.stdout)
        return False

    if rm:
        print("Cleaning up segment files...")
        for n, seguri in enumerate(segment_list, start=1):
            os.remove(seg_to_file(n, seguri))
        os.remove(index_file)

    return True


def download_segment(seguri, n, total_segments):
    """
    Download a single segment given its URI.

    Parameters:
    - seguri: The segment URI.
    - n: The segment number.
    - total_segments: The total number of segments.

    Returns:
    - True on success.
    """
    print(f"Fetching segment {n}/{total_segments} from {seguri}")
    chunk_file = seg_to_file(n, seguri)
    if os.path.exists(chunk_file):
        print(f"--> used cached: {chunk_file}")
        return True
    try:
        r = requests.get(seguri, stream=True, timeout=(5, 30))
        if r.status_code != 200:
            print(f"  * Request failed: {r.status_code}")
            return False
        with open(chunk_file, "wb") as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
        return True
    except requests.exceptions.Timeout:
        print(f"  * Request timed out for segment {n}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  * Failed to download segment {n}: {e}")
        return False


def download(segment_list):
    """
    Download all segments in `segment_list` using parallel execution.

    Parameters:
    - segment_list: A list of segment URIs.

    Returns:
    - True if all downloads were successful.
    """
    total_segments = len(segment_list)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of futures for each segment download
        futures = [
            executor.submit(download_segment, seguri, n, total_segments)
            for n, seguri in enumerate(segment_list, start=1)
        ]
        # Wait for all downloads to complete
        results = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]
    # Return True only if all downloads were successful
    return all(results)


def make_ts(t):
    """
    Parse the given time string and return a datetime object in UTC timezone.

    UTC is necessary for retrieving from the Spinitron server.

    Parameters:
    - t: A time string in the format "MM/DD/YYYY HH:MM".

    Returns:
    - A datetime object in UTC timezone.
    """
    try:
        # Parse the input time string
        localstamp = datetime.strptime(t, "%m/%d/%Y %H:%M")

        if localstamp.minute % 5 != 0:
            print("ERROR: time must be a multiple of 5 minutes")
            sys.exit(1)

        now = datetime.now()

        # Reject future dates
        if localstamp > now:
            print("ERROR: Provided date is in the future. Not allowed.")
            sys.exit(1)

        # Check if the input date is more than two weeks ago
        two_weeks_ago = now - timedelta(weeks=2)
        if localstamp < two_weeks_ago:
            print("ERROR: Provided date is greater than two weeks ago.")
            sys.exit(1)

        return localstamp.astimezone(timezone.utc)
    except ValueError as e:
        print(f"ERROR: Invalid time format - {e}")
        sys.exit(1)


def load_segs(stamp, duration_hours):
    """
    Load the segments for the given timestamp and number of hours.

    Parameters:
    - stamp: A datetime object in UTC timezone.
    - duration_hours: The number of hours to capture.

    Returns:
    - A list of segment URIs.
    """
    current_ts = stamp
    segs = []
    accum = 0  # seconds
    required = duration_hours * 60 * 60  # seconds

    # Fetch segments until we have enough content
    while accum < required:
        showtime = current_ts.strftime("%Y%m%dT%H%M00Z")
        print(f"Fetching index for {showtime}")
        try:
            playlist = m3u8.load(get_index_url(showtime))
            if len(playlist.segments) == 0:
                print("No playlist data found!")
                return []
        except HTTPError as e:
            if e.code == 404:
                print(
                    f"404 Error: Playlist for {showtime} not found. Try waiting an hour..."
                )
                return []
            print(f"HTTPError occurred: {e}")
            return []

        total_secs = 0
        for seg in playlist.segments:
            if total_secs + seg.duration > 30 * 60:
                break
            segs.append(seg.uri)
            total_secs += seg.duration
            accum += seg.duration
            if accum >= required:
                break

        if total_secs == 0:
            print("Playlist has no content!")
            return []
        if accum >= required:
            break
        print(f" --> has {total_secs} seconds (need {required - accum} more)")
        current_ts += timedelta(minutes=30)

    return segs


def generate_new_file_name(output):
    """
    Generate a new file name by appending a number if the file already exists.

    Parameters:
    - output: The original file name.

    Returns:
    - A new file name string with a number appended.
    """
    base, ext = os.path.splitext(output)  # Split the file name and extension
    counter = 1
    new_output = f"{base}_{counter}{ext}"

    # Increment the counter until we find a file name that doesn't exist
    while os.path.exists(new_output):
        counter += 1
        new_output = f"{base}_{counter}{ext}"

    return new_output


# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("date", metavar="MM/DD/YYYY", help="The show date")
parser.add_argument("time", metavar="HH:MM", help="Starting time")
parser.add_argument("count", type=int, metavar="N", help="hours (1 or 2)")
parser.add_argument("--station", default="default", help="Station code to use.")
parser.add_argument(
    "--keep",
    dest="keep",
    action="store_const",
    const=True,
    help="keep intermediate files around for debugging",
)
args = parser.parse_args()

with open("stations.json") as f:
    stations = json.load(f)

if args.station not in stations:
    print(f"ERROR: Station '{args.station}' not found in configuration.")
    sys.exit(1)
station_config = stations[args.station]

# Validate the hours argument
hours = args.count
if hours > 2 or hours < 1:
    print("Hours must be 1 or 2")
    sys.exit(1)

# Parse the date and time arguments
TIMESTAMP = f"{args.date} {args.time}"
utc_ts = make_ts(TIMESTAMP)

# Generate the show ID, which is the timestamp in the America/New_York timezone
show_id = utc_ts.astimezone(ZoneInfo(station_config["timezone"])).strftime("%Y-%m-%d-%H-%M")
print(f"Show start is {show_id}")

OUTFILE = f"{station_config['shortcode']}_{show_id}_{hours}h.mp4"

# Automatically generate a new file name if the output file already exists
if os.path.exists(OUTFILE):
    OUTFILE = generate_new_file_name(OUTFILE)
    print(f"File already exists. Using new file name: {OUTFILE}")

seglist = load_segs(utc_ts, hours)
if seglist:
    print(f"Downloading {len(seglist)} segments...")
    if download(seglist):
        if concat(seglist, OUTFILE, not args.keep):
            print(
                f"Done! The file has been output as {OUTFILE} in the current working directory"
            )
