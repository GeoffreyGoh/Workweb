# Running the server

## Every day

Open a terminal in the project folder and run:

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Then open <http://localhost:8000> and sign in.

You will know it worked when you see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Leave that terminal open.** Closing it stops the server, and the browser will
then show `ERR_CONNECTION_REFUSED`.

**To stop it:** press `Ctrl+C` in that terminal.

`--reload` means the server restarts by itself whenever you edit a file in
`backend/`. You do not need to restart it manually.

## Without activating the virtual environment

One line, from the `backend` folder:

```powershell
.venv\Scripts\uvicorn.exe main:app --reload
```

## Git Bash instead of PowerShell

```bash
cd backend
source .venv/Scripts/activate
uvicorn main:app --reload
```

## Logins

| Username | Password   | Role  |
|----------|------------|-------|
| `admin`  | `admin123` | admin |
| `budi`   | `budi123`  | user  |
| `sari`   | `sari123`  | user  |

## First time on a new machine

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
uvicorn main:app --reload
```

## When something goes wrong

**Browser says `ERR_CONNECTION_REFUSED` / `-102`**
Nothing is listening on the port. The server is not running — start it, or the
terminal running it was closed.

**`[Errno 10048] error while attempting to bind` / address already in use**
A server is already running on port 8000. Either just use it at
<http://localhost:8000>, or find and stop the old one:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <the number above>
```

Or simply run on a different port: `uvicorn main:app --reload --port 8001`

**`uvicorn: The term 'uvicorn' is not recognized`**
The virtual environment is not active. Run `.venv\Scripts\Activate.ps1` first —
your prompt should then start with `(.venv)`.

**`ModuleNotFoundError: No module named 'models'`**
You are in the wrong folder. `uvicorn` must be run from inside `backend/`.

**Resetting the demo data**
Stop the server first — Windows will not delete the file while it is open.

```powershell
del q2o.db
python seed.py
```

## Running the tests

Separate from the server; they use their own in-memory database and never touch
`q2o.db`, so you can run them while the server is up.

```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest
```
