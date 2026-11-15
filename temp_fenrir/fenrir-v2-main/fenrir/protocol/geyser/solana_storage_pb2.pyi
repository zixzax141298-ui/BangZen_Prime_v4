from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class RewardType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    Unspecified: _ClassVar[RewardType]
    Fee: _ClassVar[RewardType]
    Rent: _ClassVar[RewardType]
    Staking: _ClassVar[RewardType]
    Voting: _ClassVar[RewardType]
    DeactivatedStake: _ClassVar[RewardType]

Unspecified: RewardType
Fee: RewardType
Rent: RewardType
Staking: RewardType
Voting: RewardType
DeactivatedStake: RewardType

class ConfirmedBlock(_message.Message):
    __slots__ = (
        "block_height",
        "block_time",
        "blockhash",
        "num_partitions",
        "parent_slot",
        "previous_blockhash",
        "rewards",
        "transactions",
    )
    PREVIOUS_BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    PARENT_SLOT_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    REWARDS_FIELD_NUMBER: _ClassVar[int]
    BLOCK_TIME_FIELD_NUMBER: _ClassVar[int]
    BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    NUM_PARTITIONS_FIELD_NUMBER: _ClassVar[int]
    previous_blockhash: str
    blockhash: str
    parent_slot: int
    transactions: _containers.RepeatedCompositeFieldContainer[ConfirmedTransaction]
    rewards: _containers.RepeatedCompositeFieldContainer[Reward]
    block_time: UnixTimestamp
    block_height: BlockHeight
    num_partitions: NumPartitions
    def __init__(
        self,
        previous_blockhash: str | None = ...,
        blockhash: str | None = ...,
        parent_slot: int | None = ...,
        transactions: _Iterable[ConfirmedTransaction | _Mapping] | None = ...,
        rewards: _Iterable[Reward | _Mapping] | None = ...,
        block_time: UnixTimestamp | _Mapping | None = ...,
        block_height: BlockHeight | _Mapping | None = ...,
        num_partitions: NumPartitions | _Mapping | None = ...,
    ) -> None: ...

class ConfirmedTransaction(_message.Message):
    __slots__ = ("meta", "transaction")
    TRANSACTION_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    transaction: Transaction
    meta: TransactionStatusMeta
    def __init__(
        self,
        transaction: Transaction | _Mapping | None = ...,
        meta: TransactionStatusMeta | _Mapping | None = ...,
    ) -> None: ...

class Transaction(_message.Message):
    __slots__ = ("message", "signatures")
    SIGNATURES_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    signatures: _containers.RepeatedScalarFieldContainer[bytes]
    message: Message
    def __init__(
        self,
        signatures: _Iterable[bytes] | None = ...,
        message: Message | _Mapping | None = ...,
    ) -> None: ...

class Message(_message.Message):
    __slots__ = (
        "account_keys",
        "address_table_lookups",
        "config",
        "header",
        "instructions",
        "recent_blockhash",
        "versioned",
    )
    HEADER_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_KEYS_FIELD_NUMBER: _ClassVar[int]
    RECENT_BLOCKHASH_FIELD_NUMBER: _ClassVar[int]
    INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    VERSIONED_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_TABLE_LOOKUPS_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    header: MessageHeader
    account_keys: _containers.RepeatedScalarFieldContainer[bytes]
    recent_blockhash: bytes
    instructions: _containers.RepeatedCompositeFieldContainer[CompiledInstruction]
    versioned: bool
    address_table_lookups: _containers.RepeatedCompositeFieldContainer[
        MessageAddressTableLookup
    ]
    config: TransactionConfig
    def __init__(
        self,
        header: MessageHeader | _Mapping | None = ...,
        account_keys: _Iterable[bytes] | None = ...,
        recent_blockhash: bytes | None = ...,
        instructions: _Iterable[CompiledInstruction | _Mapping] | None = ...,
        versioned: bool | None = ...,
        address_table_lookups: (
            _Iterable[MessageAddressTableLookup | _Mapping] | None
        ) = ...,
        config: TransactionConfig | _Mapping | None = ...,
    ) -> None: ...

class TransactionConfig(_message.Message):
    __slots__ = (
        "compute_unit_limit",
        "heap_size",
        "loaded_accounts_data_size_limit",
        "priority_fee",
    )
    PRIORITY_FEE_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_UNIT_LIMIT_FIELD_NUMBER: _ClassVar[int]
    LOADED_ACCOUNTS_DATA_SIZE_LIMIT_FIELD_NUMBER: _ClassVar[int]
    HEAP_SIZE_FIELD_NUMBER: _ClassVar[int]
    priority_fee: int
    compute_unit_limit: int
    loaded_accounts_data_size_limit: int
    heap_size: int
    def __init__(
        self,
        priority_fee: int | None = ...,
        compute_unit_limit: int | None = ...,
        loaded_accounts_data_size_limit: int | None = ...,
        heap_size: int | None = ...,
    ) -> None: ...

class MessageHeader(_message.Message):
    __slots__ = (
        "num_readonly_signed_accounts",
        "num_readonly_unsigned_accounts",
        "num_required_signatures",
    )
    NUM_REQUIRED_SIGNATURES_FIELD_NUMBER: _ClassVar[int]
    NUM_READONLY_SIGNED_ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    NUM_READONLY_UNSIGNED_ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    num_required_signatures: int
    num_readonly_signed_accounts: int
    num_readonly_unsigned_accounts: int
    def __init__(
        self,
        num_required_signatures: int | None = ...,
        num_readonly_signed_accounts: int | None = ...,
        num_readonly_unsigned_accounts: int | None = ...,
    ) -> None: ...

class MessageAddressTableLookup(_message.Message):
    __slots__ = ("account_key", "readonly_indexes", "writable_indexes")
    ACCOUNT_KEY_FIELD_NUMBER: _ClassVar[int]
    WRITABLE_INDEXES_FIELD_NUMBER: _ClassVar[int]
    READONLY_INDEXES_FIELD_NUMBER: _ClassVar[int]
    account_key: bytes
    writable_indexes: bytes
    readonly_indexes: bytes
    def __init__(
        self,
        account_key: bytes | None = ...,
        writable_indexes: bytes | None = ...,
        readonly_indexes: bytes | None = ...,
    ) -> None: ...

class TransactionStatusMeta(_message.Message):
    __slots__ = (
        "compute_units_consumed",
        "cost_units",
        "err",
        "fee",
        "inner_instructions",
        "inner_instructions_none",
        "loaded_readonly_addresses",
        "loaded_writable_addresses",
        "log_messages",
        "log_messages_none",
        "post_balances",
        "post_token_balances",
        "pre_balances",
        "pre_token_balances",
        "return_data",
        "return_data_none",
        "rewards",
    )
    ERR_FIELD_NUMBER: _ClassVar[int]
    FEE_FIELD_NUMBER: _ClassVar[int]
    PRE_BALANCES_FIELD_NUMBER: _ClassVar[int]
    POST_BALANCES_FIELD_NUMBER: _ClassVar[int]
    INNER_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    INNER_INSTRUCTIONS_NONE_FIELD_NUMBER: _ClassVar[int]
    LOG_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    LOG_MESSAGES_NONE_FIELD_NUMBER: _ClassVar[int]
    PRE_TOKEN_BALANCES_FIELD_NUMBER: _ClassVar[int]
    POST_TOKEN_BALANCES_FIELD_NUMBER: _ClassVar[int]
    REWARDS_FIELD_NUMBER: _ClassVar[int]
    LOADED_WRITABLE_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    LOADED_READONLY_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    RETURN_DATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_DATA_NONE_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_UNITS_CONSUMED_FIELD_NUMBER: _ClassVar[int]
    COST_UNITS_FIELD_NUMBER: _ClassVar[int]
    err: TransactionError
    fee: int
    pre_balances: _containers.RepeatedScalarFieldContainer[int]
    post_balances: _containers.RepeatedScalarFieldContainer[int]
    inner_instructions: _containers.RepeatedCompositeFieldContainer[InnerInstructions]
    inner_instructions_none: bool
    log_messages: _containers.RepeatedScalarFieldContainer[str]
    log_messages_none: bool
    pre_token_balances: _containers.RepeatedCompositeFieldContainer[TokenBalance]
    post_token_balances: _containers.RepeatedCompositeFieldContainer[TokenBalance]
    rewards: _containers.RepeatedCompositeFieldContainer[Reward]
    loaded_writable_addresses: _containers.RepeatedScalarFieldContainer[bytes]
    loaded_readonly_addresses: _containers.RepeatedScalarFieldContainer[bytes]
    return_data: ReturnData
    return_data_none: bool
    compute_units_consumed: int
    cost_units: int
    def __init__(
        self,
        err: TransactionError | _Mapping | None = ...,
        fee: int | None = ...,
        pre_balances: _Iterable[int] | None = ...,
        post_balances: _Iterable[int] | None = ...,
        inner_instructions: _Iterable[InnerInstructions | _Mapping] | None = ...,
        inner_instructions_none: bool | None = ...,
        log_messages: _Iterable[str] | None = ...,
        log_messages_none: bool | None = ...,
        pre_token_balances: _Iterable[TokenBalance | _Mapping] | None = ...,
        post_token_balances: _Iterable[TokenBalance | _Mapping] | None = ...,
        rewards: _Iterable[Reward | _Mapping] | None = ...,
        loaded_writable_addresses: _Iterable[bytes] | None = ...,
        loaded_readonly_addresses: _Iterable[bytes] | None = ...,
        return_data: ReturnData | _Mapping | None = ...,
        return_data_none: bool | None = ...,
        compute_units_consumed: int | None = ...,
        cost_units: int | None = ...,
    ) -> None: ...

class TransactionError(_message.Message):
    __slots__ = ("err",)
    ERR_FIELD_NUMBER: _ClassVar[int]
    err: bytes
    def __init__(self, err: bytes | None = ...) -> None: ...

class InnerInstructions(_message.Message):
    __slots__ = ("index", "instructions")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    index: int
    instructions: _containers.RepeatedCompositeFieldContainer[InnerInstruction]
    def __init__(
        self,
        index: int | None = ...,
        instructions: _Iterable[InnerInstruction | _Mapping] | None = ...,
    ) -> None: ...

class InnerInstruction(_message.Message):
    __slots__ = ("accounts", "data", "program_id_index", "stack_height")
    PROGRAM_ID_INDEX_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    STACK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    program_id_index: int
    accounts: bytes
    data: bytes
    stack_height: int
    def __init__(
        self,
        program_id_index: int | None = ...,
        accounts: bytes | None = ...,
        data: bytes | None = ...,
        stack_height: int | None = ...,
    ) -> None: ...

class CompiledInstruction(_message.Message):
    __slots__ = ("accounts", "data", "program_id_index")
    PROGRAM_ID_INDEX_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTS_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    program_id_index: int
    accounts: bytes
    data: bytes
    def __init__(
        self,
        program_id_index: int | None = ...,
        accounts: bytes | None = ...,
        data: bytes | None = ...,
    ) -> None: ...

class TokenBalance(_message.Message):
    __slots__ = ("account_index", "mint", "owner", "program_id", "ui_token_amount")
    ACCOUNT_INDEX_FIELD_NUMBER: _ClassVar[int]
    MINT_FIELD_NUMBER: _ClassVar[int]
    UI_TOKEN_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    OWNER_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    account_index: int
    mint: str
    ui_token_amount: UiTokenAmount
    owner: str
    program_id: str
    def __init__(
        self,
        account_index: int | None = ...,
        mint: str | None = ...,
        ui_token_amount: UiTokenAmount | _Mapping | None = ...,
        owner: str | None = ...,
        program_id: str | None = ...,
    ) -> None: ...

class UiTokenAmount(_message.Message):
    __slots__ = ("amount", "decimals", "ui_amount", "ui_amount_string")
    UI_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    DECIMALS_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    UI_AMOUNT_STRING_FIELD_NUMBER: _ClassVar[int]
    ui_amount: float
    decimals: int
    amount: str
    ui_amount_string: str
    def __init__(
        self,
        ui_amount: float | None = ...,
        decimals: int | None = ...,
        amount: str | None = ...,
        ui_amount_string: str | None = ...,
    ) -> None: ...

class ReturnData(_message.Message):
    __slots__ = ("data", "program_id")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    program_id: bytes
    data: bytes
    def __init__(
        self, program_id: bytes | None = ..., data: bytes | None = ...
    ) -> None: ...

class Reward(_message.Message):
    __slots__ = (
        "commission",
        "commission_bps",
        "lamports",
        "post_balance",
        "pubkey",
        "reward_type",
    )
    PUBKEY_FIELD_NUMBER: _ClassVar[int]
    LAMPORTS_FIELD_NUMBER: _ClassVar[int]
    POST_BALANCE_FIELD_NUMBER: _ClassVar[int]
    REWARD_TYPE_FIELD_NUMBER: _ClassVar[int]
    COMMISSION_FIELD_NUMBER: _ClassVar[int]
    COMMISSION_BPS_FIELD_NUMBER: _ClassVar[int]
    pubkey: str
    lamports: int
    post_balance: int
    reward_type: RewardType
    commission: str
    commission_bps: str
    def __init__(
        self,
        pubkey: str | None = ...,
        lamports: int | None = ...,
        post_balance: int | None = ...,
        reward_type: RewardType | str | None = ...,
        commission: str | None = ...,
        commission_bps: str | None = ...,
    ) -> None: ...

class Rewards(_message.Message):
    __slots__ = ("num_partitions", "rewards")
    REWARDS_FIELD_NUMBER: _ClassVar[int]
    NUM_PARTITIONS_FIELD_NUMBER: _ClassVar[int]
    rewards: _containers.RepeatedCompositeFieldContainer[Reward]
    num_partitions: NumPartitions
    def __init__(
        self,
        rewards: _Iterable[Reward | _Mapping] | None = ...,
        num_partitions: NumPartitions | _Mapping | None = ...,
    ) -> None: ...

class UnixTimestamp(_message.Message):
    __slots__ = ("timestamp",)
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    def __init__(self, timestamp: int | None = ...) -> None: ...

class BlockHeight(_message.Message):
    __slots__ = ("block_height",)
    BLOCK_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    block_height: int
    def __init__(self, block_height: int | None = ...) -> None: ...

class NumPartitions(_message.Message):
    __slots__ = ("num_partitions",)
    NUM_PARTITIONS_FIELD_NUMBER: _ClassVar[int]
    num_partitions: int
    def __init__(self, num_partitions: int | None = ...) -> None: ...
