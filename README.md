# Cheat-Detection-System-for-BBMOFSGs
A proof-of-concept prototype designed to detect malicious behavior in **Blockchain-Based Multiplayer Online First-Person Shooter Games (BBMOFSGs)** using an ethical local telemetry capturer (keylogger/mouse macro recorder), off-chain storage optimization via IPFS, and smart contract auditability.
# Cheat Detection System for Blockchain-Based Online Multiplayer FPS Games

A rule-based, blockchain-verified anti-cheat system designed for Play-to-Earn (P2E) FPS games. Built as part of a final-year capstone project investigating how Proof-of-Stake blockchain consensus can be used as an anti-cheat mechanism.

## Why this exists

Cheating (aimbots, wallhacks, speed hacks, bots) undermines fairness in P2E games where in-game performance translates directly into real-world value. This system combines:

- **Lightweight, interval-based input monitoring** to distinguish human players from bots
- **Deterministic, rule-based cheat detection** (no AI/ML inference, to keep latency low enough for live FPS gameplay)
- **IPFS** for off-chain storage of gameplay logs, avoiding blockchain congestion
- **A Solidity smart contract** that lets PoS validators independently verify flagged sessions and ban confirmed cheaters on-chain

## Architecture

```
Game Client ──> Keylogger (15s cycle / 3s capture) ──> Cheat Detection Rules
                                                              │
                                                   AES-256 (per-session key)
                                                              │
                                                          IPFS Upload
                                                              │
                                              (if flagged) Smart Contract
                                                              │
                                              Validator Review & Voting
                                                              │
                                                  Wallet Ban (on-chain)
```

### Components

| Folder | Purpose |
|---|---|
| `keylogger/` | Captures mouse/keyboard activity in 3-second bursts every 15 seconds while a game session is active. Only runs during active (non-paused) sessions. |
| `keylogger/encryption.py` | AES-256-CBC encryption with a key derived per-session (PBKDF2 from a session seed + random salt), so no single key can decrypt logs across sessions. |
| `detection/` | Rule-based (if/else) cheat checks against hardcoded thresholds: accuracy (aimbot), movement speed (speed hack), and target-acquisition distance (wallhack). |
| `ipfs/` | Uploads encrypted log blobs to IPFS, run in parallel to the blockchain to avoid bloating on-chain storage. Returns a CID used as the on-chain pointer. |
| `contracts/CheatVerification.sol` | Receives flagged cheat reports (full violation data + IPFS CID), lets registered validators vote, and bans the offending wallet once enough approvals are reached. |
| `pipeline/orchestrator.py` | Wires the above together end-to-end: sample → detect → encrypt → IPFS upload → (if flagged) submit on-chain. |

## How a cheat gets caught, step by step

1. While a match is live, the keylogger wakes every 15 seconds and actively records input for 3 seconds.
2. That input sample is paired with the player's in-game action stats for the same window (shots fired, hits, distance moved, target distance).
3. `cheat_rules.py` checks the action stats against fixed thresholds for accuracy, movement speed, and observability distance.
4. The full sample (input + action log) is AES-encrypted with a key unique to that session and uploaded to IPFS.
5. If a violation was found, the complete violation data plus the IPFS CID is submitted to `CheatVerification.sol`.
6. Validators independently pull the encrypted blob from IPFS, verify the claim, and vote. Once enough approvals are reached, the contract bans the wallet on-chain.

## Status / known gaps

This is a capstone research implementation, not production-hardened:

- Detection thresholds in `detection/cheat_rules.py` are placeholders and need calibration against real gameplay data for a specific game's movement/weapon system.
- `pipeline/orchestrator.py._get_action_log_for_window()` is a stub - it needs to be wired to your game engine's telemetry/event system to supply real per-window action stats.
- Validator collateral/staking logic (the PoS economic incentive layer) lives at the chain level and is out of scope for `CheatVerification.sol`, which only handles report submission, voting, and banning.
- No reward/prize distribution logic is implemented yet (see project proposal, Chapter IV, step 4).

## Setup

```bash
pip install -r requirements.txt
```

Requires a running IPFS daemon (`ipfs daemon`) and an Ethereum-compatible RPC endpoint (e.g. a local Hardhat/Ganache node, or your AWS Managed Blockchain PoS network) for the smart contract.
