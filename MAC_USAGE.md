# macOS Usage (阿紫 10D Stack)

## 1) Prerequisites
- macOS 13+
- `python3` (3.10+ recommended)
- Optional for panel: `python3-tk`

## 2) Run
```bash
cd /path/to/元数学
python3 run_mac.py --task help
```

Or use shell wrapper:
```bash
cd /path/to/元数学
chmod +x run_mac.sh
./run_mac.sh --task help
```

## 3) Common tasks
- Start full stack:
```bash
python3 run_mac.py --task stack-start
```
- Stop full stack:
```bash
python3 run_mac.py --task stack-stop
```
- Status:
```bash
python3 run_mac.py --task stack-status
```
- Force focus to newly fed folders:
```bash
python3 run_mac.py --task focus-file-feed-now
```
- Force one research-driven self-update cycle:
```bash
python3 run_mac.py --task deep-worker-update-once
```
- Force one ISA evolution cycle:
```bash
python3 run_mac.py --task deep-worker-isa-once
```

## 4) API keys
Set env vars in your shell profile (`~/.zshrc`):
```bash
export OPENAI_API_KEY="your_key"
export ZHIPU_API_KEY="your_key"
```
Then reload:
```bash
source ~/.zshrc
```
