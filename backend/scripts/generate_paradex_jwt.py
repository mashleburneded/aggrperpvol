import asyncio
import time
import os
import logging
from typing import Dict, List, Optional, Union, cast, Sequence
import functools

import aiohttp
from starknet_py.common import int_from_bytes
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.client import Client
from starknet_py.net.models import StarknetChainId, AddressRepresentation
from starknet_py.net.signer import BaseSigner
from starknet_py.utils.typed_data import TypedData as StarknetTypedDataDataclass
from starknet_py.utils.typed_data import get_hex, is_pointer, strip_pointer
from starknet_crypto_py import (
    get_public_key as rs_get_public_key,
    pedersen_hash as rs_pedersen_hash,
    sign as rs_sign,
)
from starkware.crypto.signature.signature import generate_k_rfc6979


# --- Configuration ---
# Paradex API URL (Testnet or Mainnet)
# Ensure this matches the environment you are targeting.
# For mainnet, it's typically "https://api.paradex.trade/v1"
PARADEX_HTTP_URL = os.getenv("PARADEX_HTTP_URL", "https://api.testnet.paradex.trade/v1") 

# --- Logging Setup ---
logging.basicConfig(
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(module)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Helper functions from tradeparadex/code-samples ---

# From helpers/utils.py
def pedersen_hash(left: int, right: int) -> int:
    return rs_pedersen_hash(left, right)

def compute_hash_on_elements(data: Sequence) -> int:
    return functools.reduce(pedersen_hash, [*data, len(data)], 0)

def message_signature(
    msg_hash: int, priv_key: int, seed: Optional[int] = None
) -> tuple[int, int]:
    k = generate_k_rfc6979(msg_hash, priv_key, seed)
    return rs_sign(private_key=priv_key, msg_hash=msg_hash, k=k)

# From helpers/typed_data.py (custom TypedData for Paradex)
class ParadexTypedData(StarknetTypedDataDataclass):
    def _encode_data(self, type_name: str, data: dict) -> List[int]:
        values = []
        for param_type_def in self.types[type_name]: # Iterate over type definitions
            # Access param.name and param.type from the type definition object
            param_name = param_type_def.get("name")
            param_type = param_type_def.get("type")
            if not param_name or not param_type:
                raise ValueError(f"Malformed type definition for {type_name}: {param_type_def}")

            encoded_value = self._encode_value(param_type, data[param_name])
            values.append(encoded_value)
        return values

    def _encode_value(self, type_name: str, value: Union[int, str, dict, list]) -> int:
        if is_pointer(type_name) and isinstance(value, list):
            type_name = strip_pointer(type_name)
            if self._is_struct(type_name):
                return compute_hash_on_elements(
                    [self.struct_hash(type_name, data) for data in value]
                )
            return compute_hash_on_elements([int(get_hex(val), 16) for val in value])

        if self._is_struct(type_name) and isinstance(value, dict):
            return self.struct_hash(type_name, value)

        value = cast(Union[int, str], value)
        # For felt, if it's already an int, use it. If string, convert from hex or encode.
        if isinstance(value, str) and not value.startswith("0x"):
             # Assuming short strings for non-hex felts if not explicitly a number
            from starknet_py.cairo.felt import encode_shortstring
            return encode_shortstring(value)
        return int(get_hex(value), 16)


    def struct_hash(self, type_name: str, data: dict) -> int:
        return compute_hash_on_elements(
            [self.type_hash(type_name), *self._encode_data(type_name, data)]
        )

    def message_hash(self, account_address: int) -> int:
        from starknet_py.cairo.felt import encode_shortstring
        message_parts = [
            encode_shortstring("StarkNet Message"),
            self.struct_hash("StarkNetDomain", cast(dict, self.domain)),
            account_address,
            self.struct_hash(self.primary_type, self.message),
        ]
        return compute_hash_on_elements(message_parts)


# From helpers/account.py (custom Account for Paradex)
class ParadexAccount(StarknetAccount):
    def __init__(
        self,
        *,
        address: AddressRepresentation,
        client: Client,
        signer: Optional[BaseSigner] = None,
        key_pair: Optional[KeyPair] = None,
        chain: Optional[StarknetChainId] = None,
    ):
        super().__init__(
            address=address, client=client, signer=signer, key_pair=key_pair, chain=chain
        )

    def sign_message(self, typed_data: Dict) -> List[int]: # Accept dict
        # Convert dict to ParadexTypedData instance before processing
        typed_data_dataclass = ParadexTypedData.from_dict(typed_data)
        msg_hash = typed_data_dataclass.message_hash(self.address)
        r, s = message_signature(msg_hash=msg_hash, priv_key=self.signer.key_pair.private_key)
        return [r, s]

# From shared/api_client_utils.py or utils.py
def get_chain_id_enum(chain_id_str: str) -> StarknetChainId:
    # Simplified: starknet.py's StarknetChainId can take int directly
    # The original code had a CustomStarknetChainId IntEnum, which is not strictly needed
    # if starknet_chain_id from config is already the correct integer value or hex string.
    # For EIP-712 domain, it's often a hex string.
    # For starknet.py Account, it expects StarknetChainId enum or its value.
    # We'll assume chain_id_str from config is the string name like "SN_MAIN" or "SN_SEPOLIA"
    # or the direct hex chain_id for the TypedData domain.
    # For the Account object, we need the enum member.
    if chain_id_str.upper() == "SN_MAIN": # Example, adjust if Paradex uses different names
        return StarknetChainId.MAINNET
    elif chain_id_str.upper() == "SN_SEPOLIA":
        return StarknetChainId.SEPOLIA_TESTNET
    # Fallback for direct integer/hex if provided by config (e.g. for custom testnets)
    try:
        return StarknetChainId(int(chain_id_str, 0)) # int(0) handles hex/dec
    except ValueError:
        # If it's a string like "SN_GOERLI" that starknet-py doesn't map directly
        # we might need to map it manually or ensure config provides the int/hex.
        # For Paradex, the config provides a string like "PARADEX_TESTNET" or "SN_MAIN"
        # which then int_from_bytes is used on.
        # Let's use int_from_bytes as in the original examples for TypedData domain.
        # The Account class chain parameter is more about client behavior.
        # For now, this function is mostly for the TypedData domain part.
        # The Account will get its chain_id via int_from_bytes on the string.
        raise ValueError(f"Unsupported chain_id string for StarknetChainId enum: {chain_id_str}")


def get_paradex_l2_account(account_address: str, account_private_key: str, paradex_config_data: dict) -> ParadexAccount:
    # Ensure account_private_key is an integer
    if isinstance(account_private_key, str):
        priv_key_int = int(account_private_key, 16)
    else:
        priv_key_int = account_private_key

    key_pair = KeyPair.from_private_key(key=priv_key_int)
    
    # The chain_id for the Account object in starknet-py
    # It can be an int or a StarknetChainId enum member.
    # The config's "starknet_chain_id" is a string like "PARADEX_TESTNET"
    # We need to convert this to an int for the Account's chain parameter.
    # starknet-py's Account class expects StarknetChainId enum or its value.
    # Let's use int_from_bytes for consistency with how TypedData domain chainId is handled.
    chain_id_for_account = int_from_bytes(paradex_config_data["starknet_chain_id"].encode("UTF-8"))


    # If paradex_config_data["starknet_chain_id"] is "SN_MAIN", use StarknetChainId.MAINNET
    # otherwise, it's a custom/testnet, pass the int value.
    try:
        sn_chain_id_enum_val = StarknetChainId[paradex_config_data["starknet_chain_id"].upper()]
    except KeyError: # Not a standard name like SN_MAIN, SN_SEPOLIA
        sn_chain_id_enum_val = chain_id_for_account


    client = FullNodeClient(node_url=paradex_config_data["starknet_fullnode_rpc_url"])
    
    account = ParadexAccount(
        client=client,
        address=account_address,
        key_pair=key_pair,
        chain=sn_chain_id_enum_val,
    )
    return account

def build_paradex_auth_message(chain_id_hex_str: str, timestamp: int, expiration: int) -> Dict:
    # chain_id_hex_str should be like "0x..." or the direct int as string
    # The TypedData domain expects 'felt' for chainId, which starknet-py handles from int/hex string.
    return {
        "message": {
            "method": "POST",
            "path": "/v1/auth", # Matching the path for JWT request
            "body": "", # Body is empty for JWT request
            "timestamp": timestamp,
            "expiration": expiration,
        },
        "domain": {"name": "Paradex", "chainId": chain_id_hex_str, "version": "1"},
        "primaryType": "Request",
        "types": {
            "StarkNetDomain": [
                {"name": "name", "type": "felt"},
                {"name": "chainId", "type": "felt"},
                {"name": "version", "type": "felt"},
            ],
            "Request": [
                {"name": "method", "type": "felt"},
                {"name": "path", "type": "felt"},
                {"name": "body", "type": "felt"},
                {"name": "timestamp", "type": "felt"},
                {"name": "expiration", "type": "felt"},
            ],
        },
    }

def flatten_signature(sig: list[int]) -> str:
    return f'["{sig[0]}","{sig[1]}"]'

async def get_paradex_system_config(paradex_http_url: str) -> Dict:
    path = "/system/config"
    full_url = f"{paradex_http_url}{path}"
    logger.info(f"Fetching Paradex system config from: {full_url}")
    async with aiohttp.ClientSession() as session:
        async with session.get(full_url) as response:
            response.raise_for_status() # Raise an exception for HTTP errors
            config_data = await response.json()
            logger.info(f"Paradex system config received: {config_data}")
            return config_data

async def generate_jwt(paradex_l2_address: str, paradex_l2_private_key: str) -> Optional[str]:
    try:
        logger.info("Attempting to generate Paradex JWT...")
        paradex_config_data = await get_paradex_system_config(PARADEX_HTTP_URL)
        
        # The chain_id for the EIP-712 domain needs to be a hex string or int.
        # The config provides starknet_chain_id as a string (e.g., "PARADEX_TESTNET").
        # int_from_bytes converts this string to its felt representation.
        domain_chain_id_felt = int_from_bytes(paradex_config_data["starknet_chain_id"].encode("UTF-8"))
        domain_chain_id_hex = hex(domain_chain_id_felt)

        account = get_paradex_l2_account(paradex_l2_address, paradex_l2_private_key, paradex_config_data)
        
        now = int(time.time())
        # JWT Expiry: 7 days from now (Paradex max is 1 week, default 30 mins)
        # The /auth endpoint's PARADEX-SIGNATURE-EXPIRATION is for the signature on the request,
        # not necessarily the JWT's own expiry, but it's good practice to align them.
        # The example used 24h for the signature expiry. Let's use 7 days for the JWT request.
        expiry = now + (7 * 24 * 60 * 60 - 60) # 7 days minus a minute for buffer

        auth_typed_data = build_paradex_auth_message(domain_chain_id_hex, now, expiry)
        
        logger.info(f"Signing message for JWT with account: {paradex_l2_address}")
        signature = account.sign_message(auth_typed_data) # Expects dict
        
        headers = {
            "PARADEX-STARKNET-ACCOUNT": paradex_l2_address,
            "PARADEX-STARKNET-SIGNATURE": flatten_signature(signature),
            "PARADEX-TIMESTAMP": str(now),
            "PARADEX-SIGNATURE-EXPIRATION": str(expiry),
        }
        
        auth_url = f"{PARADEX_HTTP_URL}/auth"
        logger.info(f"Requesting JWT from {auth_url} with headers: {headers}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, headers=headers) as response:
                resp_json = await response.json()
                if response.status == 200 and "jwt_token" in resp_json:
                    logger.info(f"Successfully obtained JWT: {resp_json['jwt_token']}")
                    return resp_json["jwt_token"]
                else:
                    logger.error(f"Failed to obtain JWT. Status: {response.status}, Response: {resp_json}")
                    return None
    except Exception as e:
        logger.error(f"Error generating JWT: {e}", exc_info=True)
        return None

async def main():
    # --- User-specific credentials ---
    # Replace with your actual Paradex L2 address and L2 private key
    # These can be passed as environment variables or command-line arguments for better security
    paradex_l2_address = os.getenv("PARADEX_L2_ADDRESS")
    paradex_l2_private_key = os.getenv("PARADEX_L2_PRIVATE_KEY")

    if not paradex_l2_address or not paradex_l2_private_key:
        print("Error: Please set PARADEX_L2_ADDRESS and PARADEX_L2_PRIVATE_KEY environment variables.")
        print("Example:")
        print("export PARADEX_L2_ADDRESS=\"0x...\"")
        print("export PARADEX_L2_PRIVATE_KEY=\"0x...\"")
        return

    jwt = await generate_jwt(paradex_l2_address, paradex_l2_private_key)
    if jwt:
        print("\nSuccessfully generated Paradex JWT:")
        print(jwt)
    else:
        print("\nFailed to generate Paradex JWT.")

if __name__ == "__main__":
    # This script requires: aiohttp, starknet-py, starknet-crypto-py
    # You can install them using:
    # pip install aiohttp "starknet-py>=0.22.0" starknet-crypto-py
    asyncio.run(main())
