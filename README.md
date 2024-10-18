# spinget

Download show audio from Spinitron's ARK player.

> [!NOTE]
> Audio is only available for two weeks from the original air date! This is a Spinitron imposed limitation necessary for compliance with certain copyright law.

## How to run

1. Make sure you have ffmpeg installed on your machine. You can download ffmpeg easily using [Homebrew](https://brew.sh) in your command line:

    ```zsh
    brew install ffmpeg
    ```

2. Install python pre-requisites:

    ```zsh
    pip3 install requests m3u8
    ```

    alternatively you can run the following from the project directory,

    ```zsh
    pip3 install -r requirements.txt
    ```

    > [!NOTE]
    > If you use Homebrew to manage your Python runtime installations, you will need to first initialize and active a virtual environment (venv).

3. Get show audio:

    ```zsh
    ./spinget.py 11/04/2021 00:00 1
    ```

The above invocation gets `1` hour of audio starting at midnight (`00:00`) on
October 4th, 2024 (`10/04/2024`).

## Issues

- This probably will not work properly across a date boundry.
- This generates intermediate files in the working directory (though they are purged upon completion).
