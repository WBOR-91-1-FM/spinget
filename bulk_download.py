#!/usr/bin/env python3
"""
Import and download multiple files from a CSV file.
"""

import csv
import re
import sys
import subprocess


def validate_time(time_arg):
    """
    Checks if the time string is in HH:MM format.
    """
    pattern = r"^([01][0-9]|2[0-3]):([0-5][0-9])$"
    return bool(re.match(pattern, time_arg))


def validate_hours(hours_arg):
    """
    Checks if the hours string is a positive integer.
    """
    pattern = r"^[1-9][0-9]*$"
    return bool(re.match(pattern, hours_arg))


def main():
    """
    Main function for processing the CSV file.
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]

    try:
        with open(input_file, "r", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                date_arg, time_arg, hours_arg = row

                # Trim leading/trailing spaces
                date_arg = date_arg.strip()
                time_arg = time_arg.strip()
                hours_arg = hours_arg.strip()

                if not validate_time(time_arg):
                    print(f"Invalid time format: '{time_arg}'")
                    continue

                if not validate_hours(hours_arg):
                    print(f"Invalid hours value: '{hours_arg}'")
                    continue

                print(f"Running: ./spinget.py {date_arg} {time_arg} {hours_arg}")
                # Call spinget.py using subprocess

                try:
                    result = subprocess.run(
                        ["python3", "spinget.py", date_arg, time_arg, hours_arg],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    print(result.stdout)
                except subprocess.CalledProcessError as e:
                    print(f"Error running spinget.py: {e.stderr}")

    except FileNotFoundError:
        print(f"File '{input_file}' not found.")
        sys.exit(1)


if __name__ == "__main__":
    main()
