orchestrator.py

Ties the full pipeline together end to end:

    1. SessionKeylogger captures a 3s input sample every 15s while the
       game session is active.
    2. Each sample is paired with the in-game action stats for that
       same window (shots fired, hits, movement, etc - fed in by the
       game client) and run through cheat_rules.evaluate_action_log().
    3. The raw sample + action log is encrypted with a per-session
       AES key (encryption.SessionEncryptor) before leaving the
       player's machine.
    4. The encrypted blob is uploaded to IPFS (ipfs_client.py),
       returning a CID. IPFS sits in parallel to the blockchain so raw
       gameplay data never has to live on-chain.
    5. If cheat_rules flags violations, a full CheatReport (all
       violation data, not just a hash) + the IPFS CID is submitted to
       the CheatVerification smart contract via web3.py.
    6. Validators on the PoS chain independently fetch the IPFS blob,
       verify, and vote; once enough approvals land, the contract bans
       the wallet (handled entirely on-chain, see CheatVerification.sol).
"""

import os
import json
import uuid
from web3 import Web3

from keylogger.keylogger import SessionKeylogger, InputSample, sample_to_json
from keylogger.encryption import SessionEncryptor
from detection.cheat_rules import evaluate_action_log, CheatReport
from ipfs.ipfs_client import IPFSLogStore


class CheatDetectionPipeline:
    def __init__(self, player_wallet: str, web3_provider_url: str,
                 contract_address: str, contract_abi: list,
                 session_seed: bytes):
        self.player_wallet = player_wallet
        self.session_id = uuid.uuid4().hex

        self.encryptor = SessionEncryptor(session_seed=session_seed)
        self.ipfs = IPFSLogStore()

        self.w3 = Web3(Web3.HTTPProvider(web3_provider_url))
        self.contract = self.w3.eth.contract(address=contract_address, abi=contract_abi)

        self.keylogger = SessionKeylogger(on_sample_ready=self._handle_sample)

    def start(self):
        self.keylogger.start_session()

    def pause(self):
        self.keylogger.pause_session()

    def resume(self):
        self.keylogger.resume_session()

    def end(self):
        self.keylogger.end_session()

    # --- internal pipeline steps -------------------------------------------------

    def _handle_sample(self, sample: InputSample):
        # 1. pull matching in-game action stats for this window from the
        #    game client (placeholder - wire this up to your game's telemetry)
        action_log = self._get_action_log_for_window(sample.timestamp)

        # 2. evaluate against hardcoded thresholds
        report = evaluate_action_log(self.player_wallet, self.session_id, action_log)

        # 3. encrypt sample + action log together before they leave the machine
        payload = json.dumps({
            "input_sample": json.loads(sample_to_json(sample)),
            "action_log": action_log,
        }).encode("utf-8")
        encrypted_blob = self.encryptor.encrypt(payload)

        # 4. upload to IPFS (parallel to chain, avoids congestion)
        cid = self.ipfs.upload(encrypted_blob)
        self.ipfs.pin(cid)

        # 5. if flagged, submit full report on-chain for validator review
        if report.is_flagged:
            self._submit_report_onchain(report, cid)

    def _get_action_log_for_window(self, window_timestamp: float) -> dict:
        """
        Placeholder: in the real game client this pulls the aggregated
        gameplay stats (shots fired, hits, distance moved, etc.) for
        the same 3-second window the keylogger just sampled. Wire this
        to your game engine's telemetry/event system.
        """
        raise NotImplementedError("Connect this to the game client's telemetry feed")

    def _submit_report_onchain(self, report: CheatReport, ipfs_cid: str):
        violations_payload = [
            (
                v.rule,
                int(v.observed_value * 1_000_000),
                int(v.threshold * 1_000_000),
                v.severity,
            )
            for v in report.violations
        ]

        session_id_bytes = Web3.keccak(text=self.session_id)

        tx = self.contract.functions.submitReport(
            self.player_wallet,
            session_id_bytes,
            ipfs_cid,
            violations_payload,
            report.severity_score,
        ).build_transaction({
            "from": os.environ["PIPELINE_SUBMITTER_ADDRESS"],
            "nonce": self.w3.eth.get_transaction_count(os.environ["PIPELINE_SUBMITTER_ADDRESS"]),
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key=os.environ["PIPELINE_SUBMITTER_PRIVATE_KEY"])
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
