ipfs_client.py

Logs are uploaded to IPFS rather than directly onto the blockchain to
avoid congesting/bloating the chain with raw gameplay data. Only the
resulting IPFS content hash (CID) - plus the cheat verdict - needs to
go on-chain afterward (see contracts/CheatVerification.sol and
pipeline/orchestrator.py).

This wraps an IPFS HTTP API client (e.g. a local IPFS daemon or
Infura/Pinata gateway). Uses `ipfshttpclient` against a local node by
default - swap the addr for a hosted pinning service in production.
"""

import ipfshttpclient


class IPFSLogStore:
    def __init__(self, addr: str = "/dns/localhost/tcp/5001/http"):
        self.client = ipfshttpclient.connect(addr)

    def upload(self, encrypted_blob: bytes) -> str:
        """Uploads an encrypted log blob to IPFS and returns its CID."""
        result = self.client.add_bytes(encrypted_blob)
        cid = result if isinstance(result, str) else result["Hash"]
        return cid

    def fetch(self, cid: str) -> bytes:
        """Retrieves the raw (still-encrypted) blob for a given CID.
        Used by validators re-checking a flagged session."""
        return self.client.cat(cid)

    def pin(self, cid: str):
        """Pins the CID so it isn't garbage collected before validators
        have a chance to review a flagged cheat report."""
        self.client.pin.add(cid)
