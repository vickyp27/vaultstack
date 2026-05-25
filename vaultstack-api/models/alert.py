from sqlalchemy import Column, Integer, String, Boolean, DateTime
from database import Base
from datetime import datetime


class AlertConfig(Base):
    __tablename__ = "alert_config"

    id              = Column(Integer, primary_key=True, default=1)
    email_enabled   = Column(Boolean, default=False)
    email_smtp_host = Column(String, default="")
    email_smtp_port = Column(Integer, default=587)
    email_username  = Column(String, default="")
    email_password  = Column(String, default="")
    email_from      = Column(String, default="")
    email_to        = Column(String, default="")   # comma-separated
    slack_enabled   = Column(Boolean, default=False)
    slack_webhook   = Column(String, default="")
    alert_on_failure = Column(Boolean, default=True)
    alert_on_success = Column(Boolean, default=False)


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    level      = Column(String, default="error")   # error | info
    channel    = Column(String, default="")        # email | slack
    subject    = Column(String, default="")
    message    = Column(String, default="")
    sent_at    = Column(DateTime, default=datetime.utcnow)
    success    = Column(Boolean, default=True)
    error_detail = Column(String, default="")
