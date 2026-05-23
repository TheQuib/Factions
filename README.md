# Factions

Simple screensaver-style interactive Factions RTS. Runs in Docker. Made to run in Linux.

<br>

# Running Factions
It is recommended to run Factions as a container for ease of use and portability, but you can run locally using the included `run.sh` script.

## Build locally
### Requirements
 - Python 3.12+

### Install prerequisites
```Bash
python3 -m pip install requirements.txt
```

### Create database file
Factions stores data in a single SQLite file. Create it in the project parent directory with:
```Bash
touch factions.db
```

### Run server
```Bash
./run.sh
```

Note, the default port is `8000`, you can specify your preferred port as the first positional argument. Example:

```Bash
./run.sh 8001
```

<br>

## Docker [RECOMMENDED]
First, you'll need to install the Docker engine on your computer.

Follow [Docker's Instructions for your system](https://docs.docker.com/engine/install/) to install.

## Create database file
Factions stores data in a single SQLite file. Create it in the project parent directory with:
```Bash
touch factions.db
```

## Run the container

Clone this repository to your computer:
```Bash
git clone https://github.com/TheQuib/Factions
cd Factions
```

Run the container:
```Bash
docker compose up -d
```

## Build locally

If you prefer to build the container locally, the Dockerfile is included in this repo.

Build and run the container:
```Bash
docker compose up -d --build
````