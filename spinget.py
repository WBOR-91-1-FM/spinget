#!/usr/bin/env python3
"""
This script captures a radio show and saves it as an mp3 file.
It fetches the stream using m3u8 and concatenates the downloaded segments.

Usage:
    python3 spinget.py MM/DD/YYYY HH:MM hours

Example:
    python3 spinget.py 11/20/2021 10:00 1
    Capture 1 hour show starting at 10:00am on November 20, 2021.

Requires ffmpeg and appropriate Python packages (m3u8, requests, dotenv).

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

import m3u8
import requests
from dotenv import load_dotenv
load_dotenv()

STATION_SHORTCODE = os.getenv("STATION_SHORTCODE")

INDEXURL = (
    "https://ark3.spinitron.com/ark2/{0}-{1}/index.m3u8"
    # Pass in the station shortcode and a UTC timestamp
)

def segtofile(n, seguri):
    """
    Given a segment URI, return a unique filename for the segment.
    
    Returns a string.
    """
    chunk_id = seguri.split("/")[-1]
    return f"{STATION_SHORTCODE}_{n:05d}_{chunk_id}.tmp.mpeg"


def concat(segment_list, output, rm):
    """
    Concatenate the segments in `segment_list` into a single file named `output`.
    If `rm` is set True then also delete the downloaded segments if concatenation succeeds.
    
    Returns True on success.
    """
    print(f"Creating index file for {len(segment_list)} segments...")
    indexfn = f"{output}.index"
    with open(indexfn, "w", encoding="utf-8") as fdout:
        for n, seguri in enumerate(segment_list, start=1):
            fn = segtofile(n, seguri)
            fdout.write(f"file {fn}\n")

    print("Concatenating with ffmpeg...")
    ffproc = subprocess.run(
        [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", indexfn, "-c", "copy", output,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True
    )

    if ffproc.returncode != 0:
        print("ffmpeg run failed! Output:")
        print(ffproc.stdout)
        return False

    if rm:
        print("Cleaning up segment files...")
        for n, seguri in enumerate(segment_list, start=1):
            os.remove(segtofile(n, seguri))
        os.remove(indexfn)

    return True


def download_segment(seguri, n, total_segments):
    """
    Download a single segment given its URI.
    
    Returns True on success.
    """
    print(f"Fetching segment {n}/{total_segments} from {seguri}")
    chunk_file = segtofile(n, seguri)
    if os.path.exists(chunk_file):
        print(f"--> using cached: {chunk_file}")
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
    
    Returns True on success.
    """
    total_segments = len(segment_list)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of futures for each segment download
        futures = [
            executor.submit(download_segment, seguri, n, total_segments)
            for n, seguri in enumerate(segment_list, start=1)
        ]
        # Wait for all downloads to complete
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    # Return True only if all downloads were successful
    return all(results)


def makets(t):
    """
    Parse the given time string and return a datetime object in UTC timezone.
    
    Returns a datetime object in UTC timezone.
    """
    try:
        localstamp = datetime.strptime(t, "%m/%d/%Y %H:%M")

        if localstamp.minute % 5 != 0:
            print("ERROR: time must be a multiple of 5 minutes")
            sys.exit(1)
        # Check if the input date is more than two weeks ago
        now = datetime.now()
        two_weeks_ago = now - timedelta(weeks=2)
        if localstamp < two_weeks_ago:
            print("ERROR: Provided date is greater than two weeks ago.")
            sys.exit(1)

        return localstamp.astimezone(timezone.utc)

    except ValueError as e:
        print(f"ERROR: Invalid time format - {e}")
        sys.exit(1)


def loadsegs(stamp, duration_hours):
    """
    Load the segments for the given timestamp and number of hours.
    
    Returns a list of segment URIs.
    """
    curts = stamp
    segs = []
    accum = 0  # seconds
    required = duration_hours * 60 * 60  # seconds

    while accum < required:
        showtime = curts.strftime("%Y%m%dT%H%M00Z")
        print(f"Fetching index for {showtime}")
        try:
            playlist = m3u8.load(INDEXURL.format(STATION_SHORTCODE, showtime))
            if len(playlist.segments) == 0:
                print("No playlist data found!")
                return []
        except HTTPError as e:
            if e.code == 404:
                print(f"404 Error: Playlist for {showtime} not found. Try waiting an hour...")
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
        curts += timedelta(minutes=30)

    return segs


def generate_new_filename(output):
    """
    Generate a new filename by appending a number if the file already exists.
    """
    base, ext = os.path.splitext(output)
    counter = 1
    new_output = f"{base}_{counter}{ext}"
    while os.path.exists(new_output):
        counter += 1
        new_output = f"{base}_{counter}{ext}"
    return new_output


# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("date", metavar="MM/DD/YYYY", help="The show date")
parser.add_argument("time", metavar="HH:MM", help="Starting time")
parser.add_argument("count", type=int, metavar="N", help="hours (1 or 2)")
parser.add_argument(
    "--keep", dest="keep", action="store_const", const=True, help="keep intermediate files around",
)
args = parser.parse_args()

# Validate the hours argument
hours = args.count
if hours > 2 or hours < 1:
    print("Hours must be 1 or 2")
    sys.exit(1)

# Parse the date and time arguments
TIMESTAMP = f"{args.date} {args.time}"
utcs = makets(TIMESTAMP)

# Generate the show ID
showID = utcs.strftime("%Y%m%dT%H%M00Z")
print(f"Show start is {showID}")

OUTFILE = f"{STATION_SHORTCODE}_{showID}_{hours}h.mp4"

# Automatically generate a new filename if the output file already exists
if os.path.exists(OUTFILE):
    OUTFILE = generate_new_filename(OUTFILE)
    print(f"File already exists. Using new filename: {OUTFILE}")

seglist = loadsegs(utcs, hours)
if seglist:
    print(f"Downloading {len(seglist)} segments...")
    if download(seglist):
        if concat(seglist, OUTFILE, not args.keep):
            print(f"Done! The file has been output as {OUTFILE} in the current working directory")
