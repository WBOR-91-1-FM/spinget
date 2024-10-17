#!/usr/bin/env python3

# usage:
#
# python3 spinget.py 11/20/2021 10:00 1
#     capture 1 hour show starting at 10:00am on November 20, 2021.
#
# Requires ffmpeg
#
# version 2.1, by mathias for WXOX
# version 2.2, by Mason Daugherty for WBOR

import argparse
from datetime import datetime, date, time, timezone, timedelta
import os
import subprocess
import sys

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
    chunkID = seguri.split("/")[-1]
    return "%s_%0.5d_%s.tmp.mpeg" % (STATION_SHORTCODE, n, chunkID)


def concat(seglist, output, rm):
    """
    Concatenate the segments in `seglist` into a single file named `output`.
    If `rm` is set True then also delete the downloaded segments if concatenation succeeds.
    
    Returns True on success.
    """
    print("Creating index file for %d segments..." % len(seglist))
    # First build an index file
    indexfn = "{0}.index".format(output)
    with open(indexfn, "w") as fdout:
        n = 0
        for seguri in seglist:
            n = n + 1
            fn = segtofile(n, seguri)
            fdout.write("file {0}\n".format(fn))

    # Then get ffmpeg to do the work:
    print("Concatenating with ffmpeg...")
    ffproc = subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "{0}".format(indexfn),
            "-c",
            "copy",
            output,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if ffproc.returncode != 0:
        print("ffmpeg run failed! Output:")
        print(ffproc.stdout)
        return False
    if rm:
        print("Cleaning up segment files...")
        n = 0
        for seguri in seglist:
            n = n + 1
            os.remove(segtofile(n, seguri))
        os.remove(indexfn)
    return True


def download(seglist):
    """
    Download all segments in `seglist` to the current directory.
    
    Returns True on success.
    """
    n = 0
    for seguri in seglist:
        n = n + 1
        print("Fetching segment %d/%d from %s" % (n, len(seglist), seguri))
        chunkFile = segtofile(n, seguri)
        if os.path.exists(chunkFile):
            print("--> using cached: {0}".format(chunkFile))
            continue
        r = requests.get(seguri, stream=True)
        if r.status_code != requests.codes.ok:
            print("  * Request failed: {0}".format(r.status_code))
            return False
        with open(chunkFile, "wb") as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)
    return True


def makets(t):
    """
    Parse the given time string and return a datetime object in UTC timezone.
    
    Returns a datetime object in UTC timezone.
    """
    try:
        # Parse the given time string using 24-hour format
        localstamp = datetime.strptime(t, "%m/%d/%Y %H:%M")

        # Ensure the minutes are a multiple of 5
        if localstamp.minute % 5 != 0:
            print("ERROR: time must be a multiple of 5 minutes")
            sys.exit(1)

        # Convert to UTC timezone
        return localstamp.astimezone(timezone.utc)

    except ValueError as e:
        print(f"ERROR: Invalid time format - {e}")
        sys.exit(1)


def loadsegs(stamp, hours):
    """
    Load the segments for the given timestamp and number of hours.
    
    Returns a list of segment URIs.
    """
    curts = stamp
    segs = []
    accum = 0  # seconds
    required = hours * 60 * 60  # seconds

    while accum < required:
        showtime = curts.strftime("%Y%m%dT%H%M00Z")
        print("Fetching index for {0}".format(showtime))
        playlist = m3u8.load(INDEXURL.format(STATION_SHORTCODE, showtime))
        if len(playlist.segments) == 0:
            print("No playlist data found!")
            return []
        total_secs = 0  # seconds from this playlist
        for seg in playlist.segments:
            if (total_secs + seg.duration) > (30 * 60):  # have we exceeded 30mins?
                break
            segs.append(seg.uri)
            total_secs = total_secs + seg.duration
            accum = accum + seg.duration
            if accum >= required:
                # we have enough seconds
                break
        if total_secs == 0:
            print("Playlist has no content!")
            return []
        if accum >= required:
            break
        else:
            print(
                " --> has {0} seconds (need {1} more)".format(
                    total_secs, required - accum
                )
            )
        curts = curts + timedelta(minutes=30)  # grab index starting at next half hour
    return segs


# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("date", metavar="MM/DD/YYYY", help="The show date")
parser.add_argument("time", metavar="HH:MM", help="Starting time")
parser.add_argument("count", type=int, metavar="N", help="hours (1 or 2)")
parser.add_argument(
    "--keep",
    dest="keep",
    action="store_const",
    const=True,
    help="keep intermediate files around",
)
args = parser.parse_args()

# Validate the hours argument
hours = args.count
if hours > 2 or hours < 1:
    print("Hours must be 1 or 2")
    sys.exit(1)

# Parse the date and time arguments
timestamp = "{0} {1}".format(args.date, args.time)
utcs = makets(timestamp)

# Generate the show ID
showID = utcs.strftime("%Y%m%dT%H%M00Z")
print("Show start is {0}".format(showID))

outfile = "{0}_{1}_{2}h.mp4".format(STATION_SHORTCODE, showID, hours)

seglist = loadsegs(utcs, hours)
if len(seglist) > 0:
    print("Downloading {0} segments...".format(len(seglist)))
    if download(seglist):
        if concat(seglist, outfile, not (args.keep)):
            print("Done! The file has been output as {0} in the current working directory".format(outfile))
