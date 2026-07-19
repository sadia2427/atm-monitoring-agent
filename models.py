from sqlalchemy import Column, Integer, String, Text
from database import Base

class Device(Base):
    __tablename__ = "Devices"

    Id = Column(Integer, primary_key=True, index=True)
    Name = Column(String, default="")
    Ip = Column(String, default="")
    Type = Column(String, default="")
    Location = Column(String, nullable=True)
    HikUsername = Column(String, nullable=True)
    HikPassword = Column(String, nullable=True)
    Notes = Column(Text, nullable=True)
    ParentNvrId = Column(Integer, nullable=True)
    
    IsOnline = Column(Integer, default=1)
    LastPingTime = Column(String, nullable=True)
    LastLatency = Column(Integer, nullable=True)
    LastPacketLoss = Column(Integer, nullable=True)
    ConsecutiveFailures = Column(Integer, default=0)
    DownSince = Column(String, nullable=True)
    
    EmailAlertSent = Column(Integer, default=0)
    SmsAlertSent = Column(Integer, default=0)
    
    NvrRecording = Column(Integer, default=0)
    NvrLastRecordingDate = Column(String, nullable=True)
    NvrHddStatus = Column(String, nullable=True)
    NvrHddCapacity = Column(String, nullable=True)
    NvrHddUsed = Column(String, nullable=True)
    
    AtmBalance = Column(Integer, nullable=True)
    AtmStatus = Column(String, nullable=True)
    AtmLastUpdated = Column(String, nullable=True)
    
    CreatedAt = Column(String, nullable=True)
    UpdatedAt = Column(String, nullable=True)


class SystemSettings(Base):
    __tablename__ = "SystemSettings"

    Id = Column(Integer, primary_key=True, index=True)
    SmtpHost = Column(String, nullable=True)
    SmtpPort = Column(String, nullable=True)
    SmtpUser = Column(String, nullable=True)
    SmtpPass = Column(String, nullable=True)
    SmtpFrom = Column(String, nullable=True)
    SmtpSecure = Column(String, nullable=True)
    EmailRecipients = Column(String, nullable=True)
    
    SmsApiUrl = Column(String, nullable=True)
    SmsApiMethod = Column(String, nullable=True)
    SmsApiHeaders = Column(String, nullable=True)
    SmsApiBodyTemplate = Column(Text, nullable=True)
    SmsRecipients = Column(String, nullable=True)
    
    PingIntervalMinutes = Column(String, nullable=True)
    NvrCheckIntervalMinutes = Column(String, nullable=True)
    EmailAlertAfterMinutes = Column(String, nullable=True)
    SmsAlertAfterMinutes = Column(String, nullable=True)
    
    AtmApiKey = Column(String, nullable=True)
    
    NtpServerIp = Column(String, nullable=True, default="10.128.92.9")
    NtpServerPort = Column(Integer, nullable=True, default=123)


class AlertLog(Base):
    __tablename__ = "AlertLogs"

    Id = Column(Integer, primary_key=True, index=True)
    DeviceId = Column(Integer)
    AlertType = Column(String, default="")
    Message = Column(Text, default="")
    Recipients = Column(String, nullable=True)
    SentAt = Column(String, nullable=True)
    Success = Column(Integer, default=0)


class User(Base):
    __tablename__ = "Users"

    Id = Column(Integer, primary_key=True, index=True)
    Username = Column(String(255), unique=True, index=True, default="")
    PasswordHash = Column(String, default="")
    Role = Column(String, default="")
    CreatedAt = Column(String, nullable=True)
