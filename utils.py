from datetime import datetime
from pytz import timezone, utc

def convert_utc_to_local(utc_dt, tz_name):
    if utc_dt.tzinfo is None:
        utc_dt = utc.localize(utc_dt)
    local_tz = timezone(tz_name)
    local_dt = utc_dt.astimezone(local_tz)
    return local_dt