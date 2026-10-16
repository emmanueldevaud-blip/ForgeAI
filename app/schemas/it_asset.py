from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from enum import Enum
from ipaddress import IPv4Network, IPv6Network
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ITAssetType(str, Enum):
    PC_WINDOWS = "pc_windows"
    PC_LINUX = "pc_linux"
    SERVER = "server"
    PRINTER = "printer"
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    ACCESS_POINT = "access_point"
    OTHER = "other"


class ITAssetStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class DiscoverySource(str, Enum):
    MANUAL = "manual"
    SNMP = "snmp"
    AGENT = "agent"
    AD = "ad"
    MESHCENTRAL = "meshcentral"
    NETWORK_SCAN = "network_scan"


class ITAlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ITAlertType(str, Enum):
    STATUS_CHANGE = "status_change"
    UNREACHABLE = "unreachable"
    HIGH_LATENCY = "high_latency"
    SNMP_ERROR = "snmp_error"
    AGENT_SILENT = "agent_silent"
    NEW_ASSET = "new_asset"
    IP_CONFLICT = "ip_conflict"
    MAC_CONFLICT = "mac_conflict"


class ITAssetBase(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    asset_type: ITAssetType
    manufacturer: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = Field(None, max_length=200)
    serial_number: Optional[str] = Field(None, max_length=200)
    ip_address: Optional[str] = Field(None, max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)
    os: Optional[str] = Field(None, max_length=100)
    os_version: Optional[str] = Field(None, max_length=100)
    os_build: Optional[str] = Field(None, max_length=50)
    os_architecture: Optional[str] = Field(None, max_length=20)  # e.g., "64-bit"
    cpu_name: Optional[str] = Field(None, max_length=200)
    cpu_cores: Optional[int] = Field(None, ge=1, le=256)
    ram_total_mb: Optional[int] = Field(None, ge=0)
    ram_free_mb: Optional[int] = Field(None, ge=0)
    disk_total_mb: Optional[int] = Field(None, ge=0)
    disk_free_mb: Optional[int] = Field(None, ge=0)
    bios_version: Optional[str] = Field(None, max_length=100)
    manufacturer_system: Optional[str] = Field(None, max_length=200)  # Dell, HP, Lenovo, etc.
    domain: Optional[str] = Field(None, max_length=200)  # Active Directory domain
    last_collection: Optional[datetime] = None
    agent_version: Optional[str] = Field(None, max_length=20)
    status: ITAssetStatus = ITAssetStatus.UNKNOWN
    discovery_source: DiscoverySource = DiscoverySource.MANUAL
    discovery_data: Optional[dict] = None
    snmp_manufacturer: Optional[str] = Field(None, max_length=200)  # Collecté via SNMP
    snmp_model: Optional[str] = Field(None, max_length=200)  # Collecté via SNMP
    snmp_firmware_version: Optional[str] = Field(None, max_length=100)  # Collecté via SNMP
    snmp_contact: Optional[str] = Field(None, max_length=200)  # Collecté via SNMP
    snmp_location: Optional[str] = Field(None, max_length=500)  # Collecté via SNMP
    room_id: Optional[int] = None
    meshcentral_id: Optional[str] = Field(None, max_length=100)
    wol_enabled: bool = False
    wol_mac: Optional[str] = Field(None, max_length=17)
    notes: Optional[str] = None
    is_active: bool = True


class ITAssetCreate(ITAssetBase):
    @field_validator('mac_address')
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.replace('-', ':').lower()
        parts = v.split(':')
        if len(parts) != 6:
            raise ValueError('Adresse MAC invalide (format XX:XX:XX:XX:XX:XX)')
        for part in parts:
            if len(part) != 2 or not all(c in '0123456789abcdef' for c in part):
                raise ValueError('Adresse MAC invalide')
        return v

    @field_validator('ip_address')
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v

    @field_validator('wol_mac')
    @classmethod
    def validate_wol_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return ITAssetCreate.validate_mac(v)


    domain: Optional[str] = Field(None, max_length=200)  # Active Directory domain
    computer_name_ad: Optional[str] = Field(None, max_length=200)  # Nom du compte ordinateur dans AD
    organizational_unit: Optional[str] = Field(None, max_length=500)  # Unité organisationnelle
    last_ad_activity: Optional[datetime] = None  # Dernière activité connue dans l'annuaire
    is_domain_joined: Optional[bool] = None  # Le poste est-il joint au domaine
    domain_last_sync: Optional[datetime] = None  # Dernière synchronisation AD


class ITAssetUpdate(BaseModel):
    reference: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    asset_type: Optional[ITAssetType] = None
    manufacturer: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = Field(None, max_length=200)
    serial_number: Optional[str] = Field(None, max_length=200)
    ip_address: Optional[str] = Field(None, max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)
    os: Optional[str] = Field(None, max_length=100)
    os_version: Optional[str] = Field(None, max_length=100)
    os_build: Optional[str] = Field(None, max_length=50)
    os_architecture: Optional[str] = Field(None, max_length=20)  # e.g., "64-bit"
    cpu_name: Optional[str] = Field(None, max_length=200)
    cpu_cores: Optional[int] = Field(None, ge=1, le=256)
    ram_total_mb: Optional[int] = Field(None, ge=0)
    ram_free_mb: Optional[int] = Field(None, ge=0)
    disk_total_mb: Optional[int] = Field(None, ge=0)
    disk_free_mb: Optional[int] = Field(None, ge=0)
    bios_version: Optional[str] = Field(None, max_length=100)
    manufacturer_system: Optional[str] = Field(None, max_length=200)  # Dell, HP, Lenovo, etc.
    domain: Optional[str] = Field(None, max_length=200)  # Active Directory domain
    last_collection: Optional[datetime] = None
    agent_version: Optional[str] = Field(None, max_length=20)
    status: Optional[ITAssetStatus] = None
    discovery_source: Optional[DiscoverySource] = None
    discovery_data: Optional[dict] = None
    room_id: Optional[int] = None
    meshcentral_id: Optional[str] = Field(None, max_length=100)
    wol_enabled: Optional[bool] = None
    wol_mac: Optional[str] = Field(None, max_length=17)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RoomSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    name: str


class BuildingSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    name: str


class SiteSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    name: str


class ITAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    description: Optional[str] = None
    asset_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    os_build: Optional[str] = None
    os_architecture: Optional[str] = None  # e.g., "64-bit"
    cpu_name: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_total_mb: Optional[int] = None
    ram_free_mb: Optional[int] = None
    disk_total_mb: Optional[int] = None
    disk_free_mb: Optional[int] = None
    bios_version: Optional[str] = None
    manufacturer_system: Optional[str] = None  # Dell, HP, Lenovo, etc.
    domain: Optional[str] = None  # Active Directory domain
    computer_name_ad: Optional[str] = None  # Nom du compte ordinateur dans AD
    organizational_unit: Optional[str] = None  # Unité organisationnelle
    last_ad_activity: Optional[datetime] = None  # Dernière activité connue dans l'annuaire
    is_domain_joined: Optional[bool] = None  # Le poste est-il joint au domaine
    domain_last_sync: Optional[datetime] = None  # Dernière synchronisation AD
    last_collection: Optional[datetime] = None
    agent_version: Optional[str] = None
    status: str
    discovery_source: str
    discovery_data: Optional[dict] = None
    snmp_manufacturer: Optional[str] = None  # Collecté via SNMP
    snmp_model: Optional[str] = None  # Collecté via SNMP
    snmp_firmware_version: Optional[str] = None  # Collecté via SNMP
    snmp_contact: Optional[str] = None  # Collecté via SNMP
    snmp_location: Optional[str] = None  # Collecté via SNMP
    room_id: Optional[int] = None
    room: Optional[RoomSummaryResponse] = None
    building: Optional[BuildingSummaryResponse] = None
    site: Optional[SiteSummaryResponse] = None
    meshcentral_id: Optional[str] = None
    wol_enabled: bool
    wol_mac: Optional[str] = None
    last_seen: Optional[datetime] = None
    last_check: Optional[datetime] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ITAssetSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    name: str
    asset_type: str
    status: str
    is_active: bool


class ITAssetListParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=1000)
    search: Optional[str] = Field(None, max_length=255)
    asset_type: Optional[str] = None
    status: Optional[str] = None
    room_id: Optional[int] = None
    site_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_by: Optional[str] = Field("created_at", max_length=50)
    sort_order: Optional[str] = Field("desc", pattern="^(asc|desc)$")


class ITAssetListResponse(BaseModel):
    items: List[ITAssetResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class NetworkRangeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    cidr: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    vlan_id: Optional[int] = None
    site_id: Optional[int] = None
    scan_enabled: bool = True
    scan_interval_minutes: int = Field(60, ge=1, le=10080)
    snmp_enabled: bool = False
    snmp_community: Optional[str] = Field(None, max_length=100)
    snmp_version: Optional[str] = Field(None, max_length=20)
    snmp_port: int = Field(161, ge=1, le=65535)
    is_active: bool = True


class NetworkRangeCreate(NetworkRangeBase):
    @field_validator('cidr')
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            if ':' in v:
                IPv6Network(v, strict=False)
            else:
                IPv4Network(v, strict=False)
        except ValueError:
            raise ValueError('CIDR invalide (ex: 192.168.1.0/24 ou 2001:db8::/32)')
        return v


class NetworkRangeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    cidr: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    vlan_id: Optional[int] = None
    site_id: Optional[int] = None
    scan_enabled: Optional[bool] = None
    scan_interval_minutes: Optional[int] = Field(None, ge=1, le=10080)
    snmp_enabled: Optional[bool] = None
    snmp_community: Optional[str] = Field(None, max_length=100)
    snmp_version: Optional[str] = Field(None, max_length=20)
    snmp_port: Optional[int] = Field(None, ge=1, le=65535)
    is_active: Optional[bool] = None


class NetworkRangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cidr: str
    description: Optional[str] = None
    vlan_id: Optional[int] = None
    site_id: Optional[int] = None
    scan_enabled: bool
    scan_interval_minutes: int
    snmp_enabled: bool
    snmp_community: Optional[str] = None
    snmp_version: Optional[str] = None
    snmp_port: int
    is_active: bool
    last_scan_at: Optional[datetime] = None
    last_scan_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NetworkRangeListResponse(BaseModel):
    items: List[NetworkRangeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DiscoveryLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    network_range_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    hosts_scanned: int
    hosts_found: int
    assets_created: int
    assets_updated: int
    errors: Optional[str] = None
    details: Optional[dict] = None


class AssetObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    checked_at: datetime
    status: str
    response_time_ms: Optional[int] = None
    check_method: str
    details: Optional[dict] = None


class ITAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    alert_type: str
    severity: str
    message: str
    details: Optional[dict] = None
    acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool
    resolved_at: Optional[datetime] = None
    created_at: datetime


class ITAlertAcknowledge(BaseModel):
    acknowledged: bool = True


class ITAlertResolve(BaseModel):
    resolved: bool = True


class ITAssetHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: Optional[int] = None
    change_reason: Optional[str] = None
    created_at: datetime


class ITAssetImportItem(BaseModel):
    reference: Optional[str] = None
    name: str
    description: Optional[str] = None
    asset_type: ITAssetType
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    os: Optional[str] = None
    os_version: Optional[str] = None
    status: ITAssetStatus = ITAssetStatus.UNKNOWN
    room_reference: Optional[str] = None
    room_name: Optional[str] = None
    building_reference: Optional[str] = None
    building_name: Optional[str] = None
    site_reference: Optional[str] = None
    site_name: Optional[str] = None
    meshcentral_id: Optional[str] = None
    wol_enabled: bool = False
    wol_mac: Optional[str] = None
    notes: Optional[str] = None


class ITAssetImportRequest(BaseModel):
    items: List[ITAssetImportItem]
    skip_duplicates: bool = True
    update_existing: bool = False


class ITAssetImportResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: List[str]


class MessageResponse(BaseModel):
    message: str
