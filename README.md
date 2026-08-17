# Assest_Reconciliation

## How to Run

### Prerequisites
- Python 3.9 or later
- No external packages required — standard library only

Check your Python version:
```bash
python3 --version
```

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd asset_reconciliation
```

### 2. Folder structure
You should see the following layout:
asset_reconciliation/
├── demo.py
├── README.md
├── asset_reconciliation/
│ ├── init.py
│ ├── agent.py
│ ├── models.py
│ ├── geofences.py
│ ├── sources.py
│ ├── rules.py
│ └── report.py
└── tests/
└── test_rules.py


### 3. Run the demo
Human-readable report (5 scenarios):
```bash
python3 demo.py
```

Machine-readable JSON audit trail:
```bash
python3 demo.py --json
```

### 4. Run the test suite
```bash
python3 -m unittest discover -s tests -v
```
Expected result: `Ran 16 tests` and `OK`.

### Troubleshooting
| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'asset_reconciliation'` | Running from the wrong directory | `cd` into the outer folder that directly contains `demo.py` |
| `command not found: python` | macOS/Linux use `python3` | Use `python3` instead of `python` |
| `ImportError: cannot import name '...'` | A file is empty or corrupted | Re-clone the repository fresh |
