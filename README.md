# spinget

Download show audio from Spinitron's ARK player.

> [!NOTE]
> Audio is only available for two weeks from the original air date! This is a Spinitron imposed limitation necessary for compliance with certain copyright law.

## How to run

1. Make sure you have ffmpeg installed on your machine:

    ```zsh
    brew install ffmpeg
    ```

2. Install python pre-requisites:

    ```zsh
    pip3 install requests m3u8
    ```

    alternatively,

    ```zsh
    pip3 install -r requirements.txt
    ```

3. Get show audio, eg:

    ```zsh
    ./spinget.py 11/04/2021 00:00 1
    ```

The above invocation gets `1` hour of audio starting at midnight (`00:00`) on
November 4th, 2021 (`11/04/2021`).

## Issues

- This probably will not work properly across a date boundry.
- This generates intermediate files in the working directory.
