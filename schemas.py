from pydantic import BaseModel, ConfigDict
from typing import Optional
from pydantic.alias_generators import to_snake

class Device(BaseModel):
    Id: int
    Name: str
    Ip: str
    Type: str
    Location: Optional[str] = None
    HikUsername: Optional[str] = None
    HikPassword: Optional[str] = None
    Notes: Optional[str] = None
    ParentNvrId: Optional[int] = None
    
    IsOnline: int
    LastPingTime: Optional[str] = None
    LastLatency: Optional[int] = None
    LastPacketLoss: Optional[int] = None
    ConsecutiveFailures: int
    DownSince: Optional[str] = None
    
    EmailAlertSent: int
    SmsAlertSent: int
    
    NvrRecording: int
    NvrLastRecordingDate: Optional[str] = None
    NvrHddStatus: Optional[str] = None
    NvrHddCapacity: Optional[str] = None
    NvrHddUsed: Optional[str] = None
    
    AtmBalance: Optional[int] = None
    AtmStatus: Optional[str] = None
    AtmLastUpdated: Optional[str] = None
    
    CreatedAt: Optional[str] = None
    UpdatedAt: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake,
        populate_by_name=True
    )
    
    def model_dump(self, *args, **kwargs):
        # Override to ensure by_alias is True by default for dumping
        kwargs.setdefault('by_alias', True)
        d = super().model_dump(*args, **kwargs)
        # Handle the special case where NvrLastRecordingDate maps to nvr_last_recording in JSON
        if "nvr_last_recording_date" in d:
            d["nvr_last_recording"] = d.pop("nvr_last_recording_date")
        return d


class LoginRequest(BaseModel):
    username: str
    password: str


class AlertLog(BaseModel):
    Id: int
    DeviceId: int
    AlertType: str
    Message: str
    Recipients: Optional[str] = None
    SentAt: Optional[str] = None
    Success: int

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake,
        populate_by_name=True
    )

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault('by_alias', True)
        return super().model_dump(*args, **kwargs)


class SystemSettings(BaseModel):
    SmtpHost: Optional[str] = None
    SmtpPort: Optional[str] = None
    SmtpUser: Optional[str] = None
    SmtpPass: Optional[str] = None
    SmtpFrom: Optional[str] = None
    SmtpSecure: Optional[str] = None
    EmailRecipients: Optional[str] = None
    
    SmsApiUrl: Optional[str] = None
    SmsApiMethod: Optional[str] = None
    SmsApiHeaders: Optional[str] = None
    SmsApiBodyTemplate: Optional[str] = None
    SmsRecipients: Optional[str] = None
    
    PingIntervalMinutes: Optional[str] = None
    NvrCheckIntervalMinutes: Optional[str] = None
    EmailAlertAfterMinutes: Optional[str] = None
    SmsAlertAfterMinutes: Optional[str] = None
    
    AtmApiKey: Optional[str] = None
    
    NtpServerIp: Optional[str] = None
    NtpServerPort: Optional[int] = None

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_snake,
        populate_by_name=True
    )

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault('by_alias', True)
        return super().model_dump(*args, **kwargs)

