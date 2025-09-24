# buzzline-04-data-git-hub

We can analyze and visualize different types of streaming data as the information arrives.

The producers don't change from buzzline-03-case - they write the same information to a Kafka topic, except the csv producer for the smart smoker has been modified to not run continuously. It will stop after reading all the rows in the CSV file.
The consumers have been enhanced to add visualization.

This project uses **matplotlib** and its animation capabilities for visualization.

It generates three applications:

1. A basic producer and consumer that exchange information via a dynamically updated file.
2. A JSON producer and consumer that exchange information via a Kafka topic.
3. A CSV producer and consumer that exchange information via a different Kafka topic.

All three applications produce live charts to illustrate the data.

## First, Use Tools from Module 1 and 2

Before starting, ensure you have completed the setup tasks in <https://github.com/denisecase/buzzline-01-case> and <https://github.com/denisecase/buzzline-02-case> first.
**Python 3.11 is required.**

## Second, Copy This Example Project & Rename

1. Once the tools are installed, copy/fork this project into your GitHub account
   and create your own version of this project to run and experiment with.
2. Name it `buzzline-04-yourname` where yourname is something unique to you.

Additional information about our standard professional Python project workflow is available at
<https://github.com/denisecase/pro-analytics-01>.

Use your README.md to record your workflow and commands.

---

## Task 0. If Windows, Start WSL

Launch WSL. Open a PowerShell terminal in VS Code. Run the following command:

```powershell
wsl
```

You should now be in a Linux shell (prompt shows something like `username@DESKTOP:.../repo-name$`).

Do **all** steps related to starting Kafka in this WSL window.

---

## Task 1. Start Kafka (using WSL if Windows)

In P2, you downloaded, installed, configured a local Kafka service.
Before starting, run a short prep script to ensure Kafka has a persistent data directory and meta.properties set up. This step works on WSL, macOS, and Linux - be sure you have the $ prompt and you are in the root project folder.

1. Make sure the script is executable.
2. Run the shell script to set up Kafka.
3. Cd (change directory) to the kafka directory.
4. Start the Kafka server in the foreground.
5. Keep this terminal open - Kafka will run here
6. Watch for "started (kafka.server.KafkaServer)" message

```bash
chmod +x scripts/prepare_kafka.sh
scripts/prepare_kafka.sh
cd ~/kafka
bin/kafka-server-start.sh config/kraft/server.properties
```

**Keep this terminal open!** Kafka is running and needs to stay active.

For detailed instructions, see [SETUP_KAFKA](https://github.com/denisecase/buzzline-02-case/blob/main/SETUP_KAFKA.md) from Project 2. 

---

## Task 2. Manage Local Project Virtual Environment

Open your project in VS Code and use the commands for your operating system to:

1. Create a Python virtual environment
2. Activate the virtual environment
3. Upgrade pip
4. Install from requirements.txt

### Windows

Open a new PowerShell terminal in VS Code (Terminal / New Terminal / PowerShell).

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip wheel setuptools
py -m pip install --upgrade -r requirements.txt
```

If you get execution policy error, run this first:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Mac / Linux

Open a new terminal in VS Code (Terminal / New Terminal)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade -r requirements.txt
```

---

## Task 3. Start a Basic (File-based, not Kafka) Streaming Application

This will take two terminals:

1. One to run the producer which writes to a file in the data folder.
2. Another to run the consumer which reads from the dynamically updated file.

### Producer Terminal

Start the producer to generate the messages.

In VS Code, open a NEW terminal.
Use the commands below to activate .venv, and start the producer.

Windows:

```shell
.venv\Scripts\activate
py -m producers.basic_json_producer_case
```

Mac/Linux:

```zsh
source .venv/bin/activate
python3 -m producers.basic_json_producer_case
```

### Consumer Terminal

Start the associated consumer that will process and visualize the messages.

In VS Code, open a NEW terminal in your root project folder.
Use the commands below to activate .venv, and start the consumer.

Windows:

```shell
.venv\Scripts\activate
py -m consumers.basic_json_consumer_case
```

Mac/Linux:

```zsh
source .venv/bin/activate
python3 -m consumers.basic_json_consumer_case
```

### Review the Application Code

Review the code for both the producer and the consumer.
Understand how the information is generated, written to a file, and read and processed.
Review the visualization code to see how the live chart is produced.
When done, remember to kill the associated terminals for the producer and consumer.

---

## Task 4. Start a (Kafka-based) JSON Streaming Application

This will take two terminals:

1. One to run the producer which writes to a Kafka topic.
2. Another to run the consumer which reads from that Kafka topic.

For each one, you will need to:

1. Open a new terminal.
2. Activate your .venv.
3. Know the command that works on your machine to execute python (e.g. py or python3).
4. Know how to use the -m (module flag to run your file as a module).
5. Know the full name of the module you want to run.
   - Look in the producers folder for json_producer_case.
   - Look in the consumers folder for json_consumer_case.

### Review the Application Code

Review the code for both the producer and the consumer.
Understand how the information is generated and written to a Kafka topic, and consumed from the topic and processed.
Review the visualization code to see how the live chart is produced.

Compare the non-Kafka JSON streaming application to the Kafka JSON streaming application.
By organizing code into reusable functions, which functions can be reused?
Which functions must be updated based on the sharing mechanism?
What new functions/features must be added to work with a Kafka-based streaming system?

When done, remember to kill the associated terminals for the producer and consumer.

---

## Task 5. Start a (Kafka-based) CSV Streaming Application

This will take two terminals:

1. One to run the producer which writes to a Kafka topic.
2. Another to run the consumer which reads from that Kafka topic.

For each one, you will need to:

1. Open a new terminal.
2. Activate your .venv.
3. Know the command that works on your machine to execute python (e.g. py or python3).
4. Know how to use the -m (module flag to run your file as a module).
5. Know the full name of the module you want to run.
   - Look in the producers folder for csv_producer_case.
   - Look in the consumers folder for csv_consumer_case.

### Review the Application Code

Review the code for both the producer and the consumer.
Understand how the information is generated and written to a Kafka topic, and consumed from the topic and processed.
Review the visualization code to see how the live chart is produced.

Compare the JSON application to the CSV streaming application.
By organizing code into reusable functions, which functions can be reused?
Which functions must be updated based on the type of data?
How does the visualization code get changed based on the type of data and type of chart used?
Which aspects are similar between the different types of data?

When done, remember to kill the associated terminals for the producer and consumer.

## Possible Explorations

- JSON: Process messages in batches of 5 messages.
- JSON:Limit the display to the top 3 authors.
- Modify chart appearance.
- Stream a different set of data and visualize the custom stream with an appropriate chart.
- How do we find out what types of charts are available?
- How do we find out what attributes and colors are available?

---

## How To Stop a Continuous Process

To kill the terminal, hit CTRL c (hold both CTRL key and c key down at the same time).

## Later Work Sessions

When resuming work on this project:

1. Open the project repository folder in VS Code. 
2. Start the Kafka service (use WSL if Windows) and keep the terminal running. 
3. Activate your local project virtual environment (.venv) in your OS-specific terminal.
4. Run `git pull` to get any changes made from the remote repo (on GitHub).

## After Making Useful Changes

1. Git add everything to source control (`git add .`)
2. Git commit with a -m message.
3. Git push to origin main.

```shell
git add .
git commit -m "your message in quotes"
git push -u origin main
```

## Save Space

To save disk space, you can delete the .venv folder when not actively working on this project.
You can always recreate it, activate it, and reinstall the necessary packages later.
Managing Python virtual environments is a valuable skill.

## License

This project is licensed under the MIT License as an example project.
You are encouraged to fork, copy, explore, and modify the code as you like.
See the [LICENSE](LICENSE.txt) file for more.

## Live Chart Examples

Live Bar Chart (JSON file streaming)

![Basic JSON (file-exchange)](images/live_bar_chart_basic_example.jpg)

Live Bar Chart (Kafka JSON streaming)

![JSON (Kafka)](images/live_bar_chart_example.jpg)

Live Line Chart with Alert (Kafka CSV streaming)

![CSV (Kafka)](images/live_line_chart_example.jpg)


--- Project ---

# P4: Analyzing and Visualizing Streaming Data

## Introduction
In this project, I implemented a custom real-time consumer that connects to Twelve Data via WebSocket to stream live prices and visualizes a multi-line chart of percent change since session start for three instruments across different markets:

- EUR/USD (forex)
- AAPL (U.S. equity)
- BTC/USD (crypto)

If a symbol isn’t available on the WebSocket under your plan, the app automatically falls back to Twelve Data REST /price (lightweight polling) so it still updates on the chart. If you run without an API key, the app can only seed EUR/USD (via exchangerate.host) for a minimal demo.


## Tasks
1. Clone / open the project in VS Code.
2. Create & activate a Python 3.11 virtual environment.
3. Install dependencies from requirements.txt.
4. Create .env and set TWELVE_DATA_API_KEY=... (keep it off GitHub).
5. Run the consumer and verify the live chart updates.
6. Commit & push your changes, include a screenshot for submission.


## Requirements

- Python 3.11
- A local virtual environment (`.venv`)
- Packages from `requirements.txt`:
   - `matplotlib`, `websocket-client`, `requests`, and `python-dotenv`


## Windows Setup Instructions
```shell
# 1) In VS Code terminal (PowerShell), from the project root:
py -3.11 -m venv .venv
.\.venv\Scripts\activate

# 2) Upgrade tools and install project deps
py -m pip install --upgrade pip setuptools wheel
py -m pip install --upgrade -r requirements.txt

# 3) Create .env with your Twelve Data key (see "Get a free trial API key" below)
#    File: .env   (in project root)
#    TWELVE_DATA_API_KEY=YOUR_KEY_HERE

# 4) Run the consumer
py -m consumers.project_consumer_data-git-hub
```


## macOS/Linux Setup Instructions
```bash
# 1) In the project root:
python3.11 -m venv .venv || python3 -m venv .venv
source .venv/bin/activate

# 2) Upgrade tools and install project deps
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --upgrade -r requirements.txt

# 3) Create .env with your Twelve Data key (see "Get a free trial API key" below)
#    File: .env   (in project root)
#    TWELVE_DATA_API_KEY=YOUR_KEY_HERE

# 4) Run the consumer
python3 -m consumers.project_consumer_data-git-hub
```


## Live Price (twelvedata.com WebSocket + Matplotlib)
This consumer connects to Twelve Data via WebSocket to stream live ticks and renders a multi-line Matplotlib chart of % change since session start for the configured symbols.

- If the WebSocket declines any symbol based on your plan, that symbol is backfilled via Twelve Data REST /price every ~15 seconds.
- If you run without a key, only EUR/USD can be seeded via exchangerate.host (for a minimal demo).


## Get a free trial API key (twelvedata.com)

1. Go to https://twelvedata.com/ and create a free (Basic) account.
2. After sign-up, copy your API key from the dashboard.
3. In your project root, create a file named `.env` containing:

```shell
TWELVE_DATA_API_KEY=YOUR_KEY_HERE
```
4. Confirm `.env` is git-ignored (it should already be in `.gitignore`).
5. Plan notes (Basic / trial highlights):
   - You can test WebSocket streams but some symbols may be limited by plan.
   - Each subscribed symbol on `/v1/quotes/price` consumes 1 WebSocket credit.
   - Keep your simultaneous symbol list ≤ 8 on the Basic tier.
   - If a symbol is rejected by WS, this app will auto-fallback via Twelve Data REST `/price`.

As of this version, verified symbols that work on the trial:

- `EUR/USD` (forex)
- `AAPL` (U.S. stock)
- `BTC/USD` (crypto)

These trial allowances can change—if any symbol is rejected, you’ll see a subscribe-status log, and the app will fallback to REST for that symbol.


## Changing Symbols (for higher-tier plans, see https://twelvedata.com/pricing )
Open:
```shell
consumers/project_consumer_data-git-hub.py
```

Find the `SYMBOLS` list near the top and edit it. Keep it within your WS credits:
```shell
# -------------------------------------------------------------
# Configuration      CHANGE HERE IF YOU HAVE A HIGHER-TIER PLAN ***
# -------------------------------------------------------------

# Exactly the three you requested (note: Apple is "AAPL")
SYMBOLS: List[str] = ["EUR/USD", "AAPL", "BTC/USD"]

# -------------------------------------------------------------
# Configuration      CHANGE HERE IF YOU HAVE A HIGHER-TIER PLAN ***
# -------------------------------------------------------------
```

Example change:
```shell
# -------------------------------------------------------------
# Configuration      CHANGE HERE IF YOU HAVE A HIGHER-TIER PLAN ***
# -------------------------------------------------------------

# Exactly the three you requested (note: Apple is "AAPL")
SYMBOLS: List[str] = ["EUR/USD", "AAPL", "BTC/USD", "USD.JPY", GBP/USD", "MSFT", "ETH/USD"]

# -------------------------------------------------------------
# Configuration      CHANGE HERE IF YOU HAVE A HIGHER-TIER PLAN ***
# -------------------------------------------------------------
```
Tips:
- If the WS server rejects any symbol, this app prints the full subscribe-status and will fallback to REST polling for that symbol automatically.
- You don’t need to restart for minor edits, but it’s recommended—changes are best picked up on a fresh run.


## API Key Hygiene (don’t commit secrets)
- Store the key in .env (and/or secrets/), both are git-ignored.
- Never hard-code your key in .py files.
- If you rotate keys, just update .env.


## Troubleshooting

- “subscribe-status: warning/ok with fails”
   - Your plan may not include that symbol on WS. The app logs the reject list and starts REST fallback for those symbols.

- No lines on chart
   - Give it a few seconds. Equities tick during market hours; FX depends on liquidity/time; crypto ticks 24/7. The app seeds lines via REST to show something quickly.

- Matplotlib window issues on Linux
   - Install Tk backend: sudo apt-get install python3-tk.

- Firewall/Proxy
   - WebSocket (wss://) needs outbound access. Check corporate proxies/firewalls.


## Test API key (sanity check)

Windows:
```shell
# Make sure the deps and key are set
.\.venv\Scripts\activate
py -m pip install --upgrade -r requirements.txt

# Run
py -m consumers.project_consumer_data-git-hub
```

macOS\Linux
```bash
source .venv/bin/activate
python3 -m pip install --upgrade -r requirements.txt

python3 -m consumers.project_consumer_data-git-hub
```

## Authors

Contributors names and contact info <br>
@github.com/Data-Git-Hub <br>

---

## Version History
- P4 Finl 2.1 | Modify README.md - fix formatting
- P4 Finl 2.0 | Modify project_consumer_data-git-hub, README.md
- P4 Main 1.5 | Modify project_consumer_data-git-hub, README.md
- P4 Main 1.4 | Modify project_consumer_data-git-hub, README.md
- P4 Main 1.3 | Modify project_consumer_data-git-hub, README.md
- P4 Main 1.2 | Modify project_consumer_data-git-hub, README.md - reduced the basket of live FOREX pairs from 6 to 3
- P4 Main 1.1 | Modify project_consumer_data-git-hub, Modify README.md
- P4 Main 1.0 | Add project_consumer_data-git-hub; Modify README.md
- P4 Init 0.5 | Modify .env, .gitignore, README.md
- P4 Init 0.4 | Modify requirements.txt, README.md
- P4 Init 0.3 | Modify project_consumer_data-git-hub.py, README.md
- P4 Init 0.2 | Add project_consumer_data-git-hub.py; Modify README.md
- P4 Init 0.1 | Modify README.md

## Test History
- P4 Test 1.0 | Modify README.md - Successful single FOREX run with error
- P4 Test 1.1 | Modify README.md - Successful single USD/EUR FOREX run with multiple errors
- P4 Test 1.2 | Modify README.md - Errors
