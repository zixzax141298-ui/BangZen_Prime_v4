import datetime
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

import solana_storage_pb2 as _solana_storage_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from solana_storage_pb2 import BlockHeight as BlockHeight
from solana_storage_pb2 import CompiledInstruction as CompiledInstruction
from solana_storage_pb2 import ConfirmedBlock as ConfirmedBlock
from solana_storage_pb2 import ConfirmedTransaction as ConfirmedTransaction
from solana_storage_pb2 import InnerInstruction as InnerInstruction
from solana_storage_pb2 import InnerInstructions as InnerInstructions
from solana_storage_pb2 import Message as Message
from solana_storage_pb2 import MessageAddressTableLookup as MessageAddressTableLookup
from solana_storage_pb2 import MessageHeader as MessageHeader
from solana_storage_pb2 import NumPartitions as NumPartitions
from solana_storage_pb2 import ReturnData as ReturnData
from solana_storage_pb2 import Reward as Reward
from solana_storage_pb2 import Rewards as Rewards
from solana_storage_pb2 import RewardType as RewardType
from solana_storage_pb2 import TokenBalance as TokenBalance
from solana_storage_pb2 import Transaction as Transaction
from solana_storage_pb2 import TransactionConfig as TransactionConfig
from solana_storage_pb2 import TransactionError as TransactionError
from solana_storage_pb2 import TransactionStatusMeta as TransactionStatusMeta
from solana_storage_pb2 import UiTokenAmount as UiTokenAmount
from solana_storage_pb2 import UnixTimestamp as UnixTimestamp

DESCRIPTOR: _descriptor.FileDescriptor
Unspecified: _solana_storage_pb2.RewardType
Fee: _solana_storage_pb2.RewardType
Rent: _solana_storage_pb2.RewardType
Staking: _solana_storage_pb2.RewardType
Voting: _solana_storage_pb2.RewardType
DeactivatedStake: _solana_storage_pb2.RewardType

class CommitmentLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PROCESSED: _ClassVar[CommitmentLevel]
    CONFIRMED: _ClassVar[CommitmentLevel]
    FINALIZED: _ClassVar[CommitmentLevel]

class SlotStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SLOT_PROCESSED: _ClassVar[SlotStatus]
    SLOT_CONFIRMED: _ClassVar[SlotStatus]
    SLOT_FINALIZED: _ClassVar[SlotStatus]
    SLOT_FIRST_SHRED_RECEIVED: _ClassVar[SlotStatus]
    SLOT_COMPLETED: _ClassVar[SlotStatus]
    SLOT_CREATED_BANK: _ClassVar[SlotStatus]
    SLOT_DEAD: _ClassVar[SlotStatus]

class CuckooHashAlgorithm(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SIP_HASH: _ClassVar[CuckooHashAlgorithm]

class TokenAccountExpansionControlFlag(
    int, metaclass=_enum_type_wrapper.EnumTypeWrapper
):
    __slots__ = ()
    ALL: _ClassVar[TokenAccountExpansionControlFlag]
    BALANCE_CHANGED: _ClassVar[TokenAccountExpansionControlFlag]

PROCESSED: CommitmentLevel
CONFIRMED: CommitmentLevel
FINALIZED: CommitmentLevel
SLOT_PROCESSED: SlotStatus
SLOT_CONFIRMED: SlotStatus
SLOT_FINALIZED: SlotStatus
SLOT_FIRST_SHRED_RECEIVED: SlotStatus
SLOT_COMPLETED: SlotStatus
SLOT_CREATED_BANK: SlotStatus
SLOT_DEAD: SlotStatus
SIP_HASH: CuckooHashAlgorithm
ALL: TokenAccountExpansionControlFlag
BALANCE_CHANGED: TokenAccountExpansionControlFlag

class SubscribeRequest(_message.Message):
    __slots__ = (
        "accounts",
        "accounts_data_slice",
        "blocks",
        "blocks_meta",
        "commitment",
        "entry",
        "from_slot",
        "ping",
        "slots",
        "transactions",
        "transactions_status",
    )

    class AccountsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterAccounts
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterAccounts | _Mapping | None = ...,
        ) -> None: ...

    class SlotsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterSlots
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterSlots | _Mapping | None = ...,
        ) -> None: ...

    class TransactionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterTransactions
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterTransactions | _Mapping | None = ...,
        ) -> None: ...

    class TransactionsStatusEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterTransactions
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterTransactions | _Mapping | None = ...,
        ) -> None: ...

    class BlocksEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterBlocks
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterBlocks | _Mapping | None = ...,
        ) -> None: ...

    class BlocksMetaEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterBlocksMeta
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterBlocksMeta | _Mapping | None = ...,
        ) -> None: ...

    class EntryEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterEntry
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterEntry | _Mapping | None = ...,
        ) -> None: ...

    ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    SLOTS_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONS_STATUS_FIELD_NUMBER: _ClassVar[int]
    BLOCKS_FIELD_NUMBER: _ClassVar[int]
    BLOCKS_META_FIELD_NUMBER: _ClassVar[int]
    ENTRY_FIELD_NUMBER: _ClassVar[int]
    COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTS_DATA_SLICE_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    FROM_SLOT_FIELD_NUMBER: _ClassVar[int]
    accounts: _containers.MessageMap[str, SubscribeRequestFilterAccounts]
    slots: _containers.MessageMap[str, SubscribeRequestFilterSlots]
    transactions: _containers.MessageMap[str, SubscribeRequestFilterTransactions]
    transactions_status: _containers.MessageMap[str, SubscribeRequestFilterTransactions]
    blocks: _containers.MessageMap[str, SubscribeRequestFilterBlocks]
    blocks_meta: _containers.MessageMap[str, SubscribeRequestFilterBlocksMeta]
    entry: _containers.MessageMap[str, SubscribeRequestFilterEntry]
    commitment: CommitmentLevel
    accounts_data_slice: _containers.RepeatedCompositeFieldContainer[
        SubscribeRequestAccountsDataSlice
    ]
    ping: SubscribeRequestPing
    from_slot: int
    def __init__(
        self,
        accounts: _Mapping[str, SubscribeRequestFilterAccounts] | None = ...,
        slots: _Mapping[str, SubscribeRequestFilterSlots] | None = ...,
        transactions: _Mapping[str, SubscribeRequestFilterTransactions] | None = ...,
        transactions_status: (
            _Mapping[str, SubscribeRequestFilterTransactions] | None
        ) = ...,
        blocks: _Mapping[str, SubscribeRequestFilterBlocks] | None = ...,
        blocks_meta: _Mapping[str, SubscribeRequestFilterBlocksMeta] | None = ...,
        entry: _Mapping[str, SubscribeRequestFilterEntry] | None = ...,
        commitment: CommitmentLevel | str | None = ...,
        accounts_data_slice: (
            _Iterable[SubscribeRequestAccountsDataSlice | _Mapping] | None
        ) = ...,
        ping: SubscribeRequestPing | _Mapping | None = ...,
        from_slot: int | None = ...,
    ) -> None: ...

class CuckooFilter(_message.Message):
    __slots__ = (
        "bucket_count",
        "data",
        "entries_per_bucket",
        "fingerprint_bits",
        "hash_algorithm",
        "hash_seed",
    )
    DATA_FIELD_NUMBER: _ClassVar[int]
    BUCKET_COUNT_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_PER_BUCKET_FIELD_NUMBER: _ClassVar[int]
    FINGERPRINT_BITS_FIELD_NUMBER: _ClassVar[int]
    HASH_SEED_FIELD_NUMBER: _ClassVar[int]
    HASH_ALGORITHM_FIELD_NUMBER: _ClassVar[int]
    data: bytes
    bucket_count: int
    entries_per_bucket: int
    fingerprint_bits: int
    hash_seed: int
    hash_algorithm: CuckooHashAlgorithm
    def __init__(
        self,
        data: bytes | None = ...,
        bucket_count: int | None = ...,
        entries_per_bucket: int | None = ...,
        fingerprint_bits: int | None = ...,
        hash_seed: int | None = ...,
        hash_algorithm: CuckooHashAlgorithm | str | None = ...,
    ) -> None: ...

class SubscribeRequestFilterAccounts(_message.Message):
    __slots__ = (
        "account",
        "cuckoo_accounts_filter",
        "filters",
        "nonempty_txn_signature",
        "owner",
    )
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    NONEMPTY_TXN_SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    CUCKOO_ACCOUNTS_FILTER_FIELD_NUMBER: _ClassVar[int]
    account: _containers.RepeatedScalarFieldContainer[str]
    owner: _containers.RepeatedScalarFieldContainer[str]
    filters: _containers.RepeatedCompositeFieldContainer[
        SubscribeRequestFilterAccountsFilter
    ]
    nonempty_txn_signature: bool
    cuckoo_accounts_filter: CuckooFilter
    def __init__(
        self,
        account: _Iterable[str] | None = ...,
        owner: _Iterable[str] | None = ...,
        filters: (
            _Iterable[SubscribeRequestFilterAccountsFilter | _Mapping] | None
        ) = ...,
        nonempty_txn_signature: bool | None = ...,
        cuckoo_accounts_filter: CuckooFilter | _Mapping | None = ...,
    ) -> None: ...

class SubscribeRequestFilterAccountsFilter(_message.Message):
    __slots__ = ("datasize", "lamports", "memcmp", "token_account_state")
    MEMCMP_FIELD_NUMBER: _ClassVar[int]
    DATASIZE_FIELD_NUMBER: _ClassVar[int]
    TOKEN_ACCOUNT_STATE_FIELD_NUMBER: _ClassVar[int]
    LAMPORTS_FIELD_NUMBER: _ClassVar[int]
    memcmp: SubscribeRequestFilterAccountsFilterMemcmp
    datasize: int
    token_account_state: bool
    lamports: SubscribeRequestFilterAccountsFilterLamports
    def __init__(
        self,
        memcmp: SubscribeRequestFilterAccountsFilterMemcmp | _Mapping | None = ...,
        datasize: int | None = ...,
        token_account_state: bool | None = ...,
        lamports: SubscribeRequestFilterAccountsFilterLamports | _Mapping | None = ...,
    ) -> None: ...

class SubscribeRequestFilterAccountsFilterMemcmp(_message.Message):
    __slots__ = ("base58", "base64", "bytes", "offset")
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    BYTES_FIELD_NUMBER: _ClassVar[int]
    BASE58_FIELD_NUMBER: _ClassVar[int]
    BASE64_FIELD_NUMBER: _ClassVar[int]
    offset: int
    bytes: bytes
    base58: str
    base64: str
    def __init__(
        self,
        offset: int | None = ...,
        bytes: bytes | None = ...,
        base58: str | None = ...,
        base64: str | None = ...,
    ) -> None: ...

class SubscribeRequestFilterAccountsFilterLamports(_message.Message):
    __slots__ = ("eq", "gt", "lt", "ne")
    EQ_FIELD_NUMBER: _ClassVar[int]
    NE_FIELD_NUMBER: _ClassVar[int]
    LT_FIELD_NUMBER: _ClassVar[int]
    GT_FIELD_NUMBER: _ClassVar[int]
    eq: int
    ne: int
    lt: int
    gt: int
    def __init__(
        self,
        eq: int | None = ...,
        ne: int | None = ...,
        lt: int | None = ...,
        gt: int | None = ...,
    ) -> None: ...

class SubscribeRequestFilterSlots(_message.Message):
    __slots__ = ("filter_by_commitment", "interslot_updates")
    FILTER_BY_COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    INTERSLOT_UPDATES_FIELD_NUMBER: _ClassVar[int]
    filter_by_commitment: bool
    interslot_updates: bool
    def __init__(
        self,
        filter_by_commitment: bool | None = ...,
        interslot_updates: bool | None = ...,
    ) -> None: ...

class SubscribeRequestFilterTransactions(_message.Message):
    __slots__ = (
        "account_exclude",
        "account_include",
        "account_required",
        "failed",
        "signature",
        "token_accounts",
        "vote",
    )
    VOTE_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_EXCLUDE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    TOKEN_ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    vote: bool
    failed: bool
    signature: str
    account_include: _containers.RepeatedScalarFieldContainer[str]
    account_exclude: _containers.RepeatedScalarFieldContainer[str]
    account_required: _containers.RepeatedScalarFieldContainer[str]
    token_accounts: TokenAccountExpansionControlFlag
    def __init__(
        self,
        vote: bool | None = ...,
        failed: bool | None = ...,
        signature: str | None = ...,
        account_include: _Iterable[str] | None = ...,
        account_exclude: _Iterable[str] | None = ...,
        account_required: _Iterable[str] | None = ...,
        token_accounts: TokenAccountExpansionControlFlag | str | None = ...,
    ) -> None: ...

class SubscribeRequestFilterBlocks(_message.Message):
    __slots__ = (
        "account_include",
        "cuckoo_account_include",
        "include_accounts",
        "include_entries",
        "include_transactions",
    )
    ACCOUNT_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_ENTRIES_FIELD_NUMBER: _ClassVar[int]
    CUCKOO_ACCOUNT_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    account_include: _containers.RepeatedScalarFieldContainer[str]
    include_transactions: bool
    include_accounts: bool
    include_entries: bool
    cuckoo_account_include: CuckooFilter
    def __init__(
        self,
        account_include: _Iterable[str] | None = ...,
        include_transactions: bool | None = ...,
        include_accounts: bool | None = ...,
        include_entries: bool | None = ...,
        cuckoo_account_include: CuckooFilter | _Mapping | None = ...,
    ) -> None: ...

class SubscribeRequestFilterBlocksMeta(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeRequestFilterEntry(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeRequestFilterDeshredTransactions(_message.Message):
    __slots__ = ("account_exclude", "account_include", "account_required", "vote")
    VOTE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_EXCLUDE_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    vote: bool
    account_include: _containers.RepeatedScalarFieldContainer[str]
    account_exclude: _containers.RepeatedScalarFieldContainer[str]
    account_required: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        vote: bool | None = ...,
        account_include: _Iterable[str] | None = ...,
        account_exclude: _Iterable[str] | None = ...,
        account_required: _Iterable[str] | None = ...,
    ) -> None: ...

class SubscribeRequestAccountsDataSlice(_message.Message):
    __slots__ = ("length", "offset")
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LENGTH_FIELD_NUMBER: _ClassVar[int]
    offset: int
    length: int
    def __init__(self, offset: int | None = ..., length: int | None = ...) -> None: ...

class SubscribeRequestPing(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: int | None = ...) -> None: ...

class SubscribeDeshredRequest(_message.Message):
    __slots__ = ("deshred_transactions", "ping", "slots")

    class DeshredTransactionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterDeshredTransactions
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterDeshredTransactions | _Mapping | None = ...,
        ) -> None: ...

    class SlotsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: SubscribeRequestFilterSlots
        def __init__(
            self,
            key: str | None = ...,
            value: SubscribeRequestFilterSlots | _Mapping | None = ...,
        ) -> None: ...

    DESHRED_TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    SLOTS_FIELD_NUMBER: _ClassVar[int]
    deshred_transactions: _containers.MessageMap[
        str, SubscribeRequestFilterDeshredTransactions
    ]
    ping: SubscribeRequestPing
    slots: _containers.MessageMap[str, SubscribeRequestFilterSlots]
    def __init__(
        self,
        deshred_transactions: (
            _Mapping[str, SubscribeRequestFilterDeshredTransactions] | None
        ) = ...,
        ping: SubscribeRequestPing | _Mapping | None = ...,
        slots: _Mapping[str, SubscribeRequestFilterSlots] | None = ...,
    ) -> None: ...

class SubscribeUpdate(_message.Message):
    __slots__ = (
        "account",
        "block",
        "block_meta",
        "created_at",
        "entry",
        "filters",
        "ping",
        "pong",
        "slot",
        "transaction",
        "transaction_status",
    )
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    SLOT_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_STATUS_FIELD_NUMBER: _ClassVar[int]
    BLOCK_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    PONG_FIELD_NUMBER: _ClassVar[int]
    BLOCK_META_FIELD_NUMBER: _ClassVar[int]
    ENTRY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    filters: _containers.RepeatedScalarFieldContainer[str]
    account: SubscribeUpdateAccount
    slot: SubscribeUpdateSlot
    transaction: SubscribeUpdateTransaction
    transaction_status: SubscribeUpdateTransactionStatus
    block: SubscribeUpdateBlock
    ping: SubscribeUpdatePing
    pong: SubscribeUpdatePong
    block_meta: SubscribeUpdateBlockMeta
    entry: SubscribeUpdateEntry
    created_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        filters: _Iterable[str] | None = ...,
        account: SubscribeUpdateAccount | _Mapping | None = ...,
        slot: SubscribeUpdateSlot | _Mapping | None = ...,
        transaction: SubscribeUpdateTransaction | _Mapping | None = ...,
        transaction_status: SubscribeUpdateTransactionStatus | _Mapping | None = ...,
        block: SubscribeUpdateBlock | _Mapping | None = ...,
        ping: SubscribeUpdatePing | _Mapping | None = ...,
        pong: SubscribeUpdatePong | _Mapping | None = ...,
        block_meta: SubscribeUpdateBlockMeta | _Mapping | None = ...,
        entry: SubscribeUpdateEntry | _Mapping | None = ...,
        created_at: (
            datetime.datetime | _timestamp_pb2.Timestamp | _Mapping | None
        ) = ...,
    ) -> None: ...

class SubscribeUpdateAccount(_message.Message):
    __slots__ = ("account", "is_startup", "slot")
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    SLOT_FIELD_NUMBER: _ClassVar[int]
    IS_STARTUP_FIELD_NUMBER: _ClassVar[int]
    account: SubscribeUpdateAccountInfo
    slot: int
    is_startup: bool
    def __init__(
        self,
        account: SubscribeUpdateAccountInfo | _Mapping | None = ...,
        slot: int | None = ...,
        is_startup: bool | None = ...,
    ) -> None: ...

class SubscribeUpdateAccountInfo(_message.Message):
    __slots__ = (
        "data",
        "executable",
        "lamports",
        "owner",
        "pubkey",
        "rent_epoch",
        "txn_signature",
        "write_version",
    )
    PUBKEY_FIELD_NUMBER: _ClassVar[int]
    LAMPORTS_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    EXECUTABLE_FIELD_NUMBER: _ClassVar[int]
    RENT_EPOCH_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    WRITE_VERSION_FIELD_NUMBER: _ClassVar[int]
    TXN_SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    pubkey: bytes
    lamports: int
    owner: bytes
    executable: bool
    rent_epoch: int
    data: bytes
    write_version: int
    txn_signature: bytes
    def __init__(
        self,
        pubkey: bytes | None = ...,
        lamports: int | None = ...,
        owner: bytes | None = ...,
        executable: bool | None = ...,
        rent_epoch: int | None = ...,
        data: bytes | None = ...,
        write_version: int | None = ...,
        txn_signature: bytes | None = ...,
    ) -> None: ...

class SubscribeUpdateSlot(_message.Message):
    __slots__ = ("dead_error", "parent", "slot", "status")
    SLOT_FIELD_NUMBER: _ClassVar[int]
    PARENT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DEAD_ERROR_FIELD_NUMBER: _ClassVar[int]
    slot: int
    parent: int
    status: SlotStatus
    dead_error: str
    def __init__(
        self,
        slot: int | None = ...,
        parent: int | None = ...,
        status: SlotStatus | str | None = ...,
        dead_error: str | None = ...,
    ) -> None: ...

class SubscribeUpdateTransaction(_message.Message):
    __slots__ = ("slot", "transaction")
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    SLOT_FIELD_NUMBER: _ClassVar[int]
    transaction: SubscribeUpdateTransactionInfo
    slot: int
    def __init__(
        self,
        transaction: SubscribeUpdateTransactionInfo | _Mapping | None = ...,
        slot: int | None = ...,
    ) -> None: ...

class SubscribeUpdateTransactionInfo(_message.Message):
    __slots__ = ("index", "is_vote", "meta", "signature", "transaction")
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    IS_VOTE_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    signature: bytes
    is_vote: bool
    transaction: _solana_storage_pb2.Transaction
    meta: _solana_storage_pb2.TransactionStatusMeta
    index: int
    def __init__(
        self,
        signature: bytes | None = ...,
        is_vote: bool | None = ...,
        transaction: _solana_storage_pb2.Transaction | _Mapping | None = ...,
        meta: _solana_storage_pb2.TransactionStatusMeta | _Mapping | None = ...,
        index: int | None = ...,
    ) -> None: ...

class SubscribeUpdateTransactionStatus(_message.Message):
    __slots__ = ("err", "index", "is_vote", "signature", "slot")
    SLOT_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    IS_VOTE_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    ERR_FIELD_NUMBER: _ClassVar[int]
    slot: int
    signature: bytes
    is_vote: bool
    index: int
    err: _solana_storage_pb2.TransactionError
    def __init__(
        self,
        slot: int | None = ...,
        signature: bytes | None = ...,
        is_vote: bool | None = ...,
        index: int | None = ...,
        err: _solana_storage_pb2.TransactionError | _Mapping | None = ...,
    ) -> None: ...

class SubscribeUpdateBlock(_message.Message):
    __slots__ = (
        "accounts",
        "block_height",
        "block_time",
        "blockhash",
        "entries",
        "entries_count",
        "executed_transaction_count",
        "parent_blockhash",
        "parent_slot",
        "rewards",
        "slot",
        "transactions",
        "updated_account_count",
    )
    SLOT_FIELD_NUMBER: _ClassVar[int]
    BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    REWARDS_FIELD_NUMBER: _ClassVar[int]
    BLOCK_TIME_FIELD_NUMBER: _ClassVar[int]
    BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    PARENT_SLOT_FIELD_NUMBER: _ClassVar[int]
    PARENT_BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    EXECUTED_TRANSACTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_ACCOUNT_COUNT_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_COUNT_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    slot: int
    blockhash: str
    rewards: _solana_storage_pb2.Rewards
    block_time: _solana_storage_pb2.UnixTimestamp
    block_height: _solana_storage_pb2.BlockHeight
    parent_slot: int
    parent_blockhash: str
    executed_transaction_count: int
    transactions: _containers.RepeatedCompositeFieldContainer[
        SubscribeUpdateTransactionInfo
    ]
    updated_account_count: int
    accounts: _containers.RepeatedCompositeFieldContainer[SubscribeUpdateAccountInfo]
    entries_count: int
    entries: _containers.RepeatedCompositeFieldContainer[SubscribeUpdateEntry]
    def __init__(
        self,
        slot: int | None = ...,
        blockhash: str | None = ...,
        rewards: _solana_storage_pb2.Rewards | _Mapping | None = ...,
        block_time: _solana_storage_pb2.UnixTimestamp | _Mapping | None = ...,
        block_height: _solana_storage_pb2.BlockHeight | _Mapping | None = ...,
        parent_slot: int | None = ...,
        parent_blockhash: str | None = ...,
        executed_transaction_count: int | None = ...,
        transactions: _Iterable[SubscribeUpdateTransactionInfo | _Mapping] | None = ...,
        updated_account_count: int | None = ...,
        accounts: _Iterable[SubscribeUpdateAccountInfo | _Mapping] | None = ...,
        entries_count: int | None = ...,
        entries: _Iterable[SubscribeUpdateEntry | _Mapping] | None = ...,
    ) -> None: ...

class SubscribeUpdateBlockMeta(_message.Message):
    __slots__ = (
        "block_height",
        "block_time",
        "blockhash",
        "entries_count",
        "executed_transaction_count",
        "parent_blockhash",
        "parent_slot",
        "rewards",
        "slot",
    )
    SLOT_FIELD_NUMBER: _ClassVar[int]
    BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    REWARDS_FIELD_NUMBER: _ClassVar[int]
    BLOCK_TIME_FIELD_NUMBER: _ClassVar[int]
    BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    PARENT_SLOT_FIELD_NUMBER: _ClassVar[int]
    PARENT_BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    EXECUTED_TRANSACTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_COUNT_FIELD_NUMBER: _ClassVar[int]
    slot: int
    blockhash: str
    rewards: _solana_storage_pb2.Rewards
    block_time: _solana_storage_pb2.UnixTimestamp
    block_height: _solana_storage_pb2.BlockHeight
    parent_slot: int
    parent_blockhash: str
    executed_transaction_count: int
    entries_count: int
    def __init__(
        self,
        slot: int | None = ...,
        blockhash: str | None = ...,
        rewards: _solana_storage_pb2.Rewards | _Mapping | None = ...,
        block_time: _solana_storage_pb2.UnixTimestamp | _Mapping | None = ...,
        block_height: _solana_storage_pb2.BlockHeight | _Mapping | None = ...,
        parent_slot: int | None = ...,
        parent_blockhash: str | None = ...,
        executed_transaction_count: int | None = ...,
        entries_count: int | None = ...,
    ) -> None: ...

class SubscribeUpdateEntry(_message.Message):
    __slots__ = (
        "executed_transaction_count",
        "hash",
        "index",
        "num_hashes",
        "slot",
        "starting_transaction_index",
    )
    SLOT_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NUM_HASHES_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    EXECUTED_TRANSACTION_COUNT_FIELD_NUMBER: _ClassVar[int]
    STARTING_TRANSACTION_INDEX_FIELD_NUMBER: _ClassVar[int]
    slot: int
    index: int
    num_hashes: int
    hash: bytes
    executed_transaction_count: int
    starting_transaction_index: int
    def __init__(
        self,
        slot: int | None = ...,
        index: int | None = ...,
        num_hashes: int | None = ...,
        hash: bytes | None = ...,
        executed_transaction_count: int | None = ...,
        starting_transaction_index: int | None = ...,
    ) -> None: ...

class SubscribeUpdateDeshredTransaction(_message.Message):
    __slots__ = ("slot", "transaction")
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    SLOT_FIELD_NUMBER: _ClassVar[int]
    transaction: SubscribeUpdateDeshredTransactionInfo
    slot: int
    def __init__(
        self,
        transaction: SubscribeUpdateDeshredTransactionInfo | _Mapping | None = ...,
        slot: int | None = ...,
    ) -> None: ...

class SubscribeUpdateDeshredTransactionInfo(_message.Message):
    __slots__ = (
        "completed_data_set_ending_shred_index_exclusive",
        "completed_data_set_starting_shred_index",
        "is_vote",
        "loaded_readonly_addresses",
        "loaded_writable_addresses",
        "signature",
        "transaction",
    )
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    IS_VOTE_FIELD_NUMBER: _ClassVar[int]
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    LOADED_WRITABLE_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    LOADED_READONLY_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_DATA_SET_STARTING_SHRED_INDEX_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_DATA_SET_ENDING_SHRED_INDEX_EXCLUSIVE_FIELD_NUMBER: _ClassVar[int]
    signature: bytes
    is_vote: bool
    transaction: _solana_storage_pb2.Transaction
    loaded_writable_addresses: _containers.RepeatedScalarFieldContainer[bytes]
    loaded_readonly_addresses: _containers.RepeatedScalarFieldContainer[bytes]
    completed_data_set_starting_shred_index: int
    completed_data_set_ending_shred_index_exclusive: int
    def __init__(
        self,
        signature: bytes | None = ...,
        is_vote: bool | None = ...,
        transaction: _solana_storage_pb2.Transaction | _Mapping | None = ...,
        loaded_writable_addresses: _Iterable[bytes] | None = ...,
        loaded_readonly_addresses: _Iterable[bytes] | None = ...,
        completed_data_set_starting_shred_index: int | None = ...,
        completed_data_set_ending_shred_index_exclusive: int | None = ...,
    ) -> None: ...

class SubscribeUpdatePing(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeUpdatePong(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: int | None = ...) -> None: ...

class SubscribeUpdateDeshred(_message.Message):
    __slots__ = ("created_at", "deshred_transaction", "filters", "ping", "pong", "slot")
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    DESHRED_TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    PING_FIELD_NUMBER: _ClassVar[int]
    PONG_FIELD_NUMBER: _ClassVar[int]
    SLOT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    filters: _containers.RepeatedScalarFieldContainer[str]
    deshred_transaction: SubscribeUpdateDeshredTransaction
    ping: SubscribeUpdatePing
    pong: SubscribeUpdatePong
    slot: SubscribeUpdateSlot
    created_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        filters: _Iterable[str] | None = ...,
        deshred_transaction: SubscribeUpdateDeshredTransaction | _Mapping | None = ...,
        ping: SubscribeUpdatePing | _Mapping | None = ...,
        pong: SubscribeUpdatePong | _Mapping | None = ...,
        slot: SubscribeUpdateSlot | _Mapping | None = ...,
        created_at: (
            datetime.datetime | _timestamp_pb2.Timestamp | _Mapping | None
        ) = ...,
    ) -> None: ...

class SubscribeReplayInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeReplayInfoResponse(_message.Message):
    __slots__ = ("first_available",)
    FIRST_AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    first_available: int
    def __init__(self, first_available: int | None = ...) -> None: ...

class PingRequest(_message.Message):
    __slots__ = ("count",)
    COUNT_FIELD_NUMBER: _ClassVar[int]
    count: int
    def __init__(self, count: int | None = ...) -> None: ...

class PongResponse(_message.Message):
    __slots__ = ("count",)
    COUNT_FIELD_NUMBER: _ClassVar[int]
    count: int
    def __init__(self, count: int | None = ...) -> None: ...

class GetLatestBlockhashRequest(_message.Message):
    __slots__ = ("commitment",)
    COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    commitment: CommitmentLevel
    def __init__(self, commitment: CommitmentLevel | str | None = ...) -> None: ...

class GetLatestBlockhashResponse(_message.Message):
    __slots__ = ("blockhash", "last_valid_block_height", "slot")
    SLOT_FIELD_NUMBER: _ClassVar[int]
    BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    LAST_VALID_BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    slot: int
    blockhash: str
    last_valid_block_height: int
    def __init__(
        self,
        slot: int | None = ...,
        blockhash: str | None = ...,
        last_valid_block_height: int | None = ...,
    ) -> None: ...

class GetBlockHeightRequest(_message.Message):
    __slots__ = ("commitment",)
    COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    commitment: CommitmentLevel
    def __init__(self, commitment: CommitmentLevel | str | None = ...) -> None: ...

class GetBlockHeightResponse(_message.Message):
    __slots__ = ("block_height",)
    BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    block_height: int
    def __init__(self, block_height: int | None = ...) -> None: ...

class GetSlotRequest(_message.Message):
    __slots__ = ("commitment",)
    COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    commitment: CommitmentLevel
    def __init__(self, commitment: CommitmentLevel | str | None = ...) -> None: ...

class GetSlotResponse(_message.Message):
    __slots__ = ("slot",)
    SLOT_FIELD_NUMBER: _ClassVar[int]
    slot: int
    def __init__(self, slot: int | None = ...) -> None: ...

class GetVersionRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetVersionResponse(_message.Message):
    __slots__ = ("version",)
    VERSION_FIELD_NUMBER: _ClassVar[int]
    version: str
    def __init__(self, version: str | None = ...) -> None: ...

class IsBlockhashValidRequest(_message.Message):
    __slots__ = ("blockhash", "commitment")
    BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    COMMITMENT_FIELD_NUMBER: _ClassVar[int]
    blockhash: str
    commitment: CommitmentLevel
    def __init__(
        self,
        blockhash: str | None = ...,
        commitment: CommitmentLevel | str | None = ...,
    ) -> None: ...

class IsBlockhashValidResponse(_message.Message):
    __slots__ = ("slot", "valid")
    SLOT_FIELD_NUMBER: _ClassVar[int]
    VALID_FIELD_NUMBER: _ClassVar[int]
    slot: int
    valid: bool
    def __init__(self, slot: int | None = ..., valid: bool | None = ...) -> None: ...
