# luz-clock

Date and time utilities included with Luz. No installation needed.

```
import "clock"
```

---

## Moment

### `now()`
Returns a dict with all components of the current local time.

| Key | Description |
|---|---|
| `year` | Four-digit year |
| `month` | Month (1–12) |
| `day` | Day of month (1–31) |
| `hour` | Hour (0–23) |
| `min` | Minute (0–59) |
| `sec` | Second (0–59) |
| `ms` | Milliseconds (0–999) |
| `weekday` | Day of week (0=Monday … 6=Sunday) |
| `yearday` | Day of year (1–366) |

```
t = now()
write(t["year"])    # 2026
write(t["hour"])    # 17
```

### `today()`
Returns only the date part: `{year, month, day}`.

```
d = today()
write($"{d["year"]}-{d["month"]}-{d["day"]}")   # 2026-3-22
```

### `current_time()`
Returns only the time part: `{hour, min, sec, ms}`.

```
t = current_time()
write($"{t["hour"]}:{t["min"]}:{t["sec"]}")   # 17:05:42
```

### `stamp()`
Returns the current Unix timestamp (seconds since 1970-01-01) as a float.

```
ts = stamp()
write(ts)   # 1774210625.83
```

---

## Format

### `fmt(pattern)`
Formats the current date/time using a pattern string.

| Pattern | Output |
|---|---|
| `%Y` | Four-digit year |
| `%m` | Month (01–12) |
| `%d` | Day (01–31) |
| `%H` | Hour 24h (00–23) |
| `%M` | Minute (00–59) |
| `%S` | Second (00–59) |
| `%A` | Full weekday name |
| `%B` | Full month name |
| `%I` | Hour 12h (01–12) |
| `%p` | AM/PM |

```
write(fmt("%Y-%m-%d"))           # 2026-03-22
write(fmt("%H:%M:%S"))           # 17:05:42
write(fmt("%A, %B %d %Y"))       # Sunday, March 22 2026
```

### `day_name(n)` / `day_short(n)`
Returns the full or abbreviated name of a weekday (0=Monday … 6=Sunday).

```
write(day_name(0))    # Monday
write(day_short(6))   # Sun
```

### `month_name(n)` / `month_short(n)`
Returns the full or abbreviated name of a month (1–12).

```
write(month_name(3))    # March
write(month_short(12))  # Dec
```

### `is_leap(yr)`
Returns `true` if the given year is a leap year.

```
write(is_leap(2024))   # true
write(is_leap(2025))   # false
```

---

## Calc

### `since(ts)`
Returns the seconds elapsed since a Unix timestamp.

```
start = stamp()
# ... do something ...
write(since(start))   # 0.003
```

### `diff(ts1, ts2)`
Returns the absolute difference in seconds between two timestamps.

```
write(diff(1000, 1600))   # 600
```

### `add_secs(ts, n)` / `add_mins(ts, n)` / `add_hours(ts, n)` / `add_days(ts, n)`
Returns a new timestamp offset by the given amount.

```
ts = stamp()
tomorrow = add_days(ts, 1)
next_hour = add_hours(ts, 1)
```

### `from_stamp(ts)`
Converts a Unix timestamp to a time dict (same format as `now()`).

```
t = from_stamp(0)
write(t["year"])   # 1970
```

### `parse_stamp(date_str, pattern)`
Parses a date string into a Unix timestamp.

```
ts = parse_stamp("2025-01-15", "%Y-%m-%d")
write(from_stamp(ts)["year"])   # 2025
```

### `to_secs(h, m, s)`
Converts hours, minutes, seconds to total seconds.

```
write(to_secs(1, 30, 0))   # 5400
```

### `from_secs(total)`
Breaks a total seconds value into `{hours, mins, secs}`.

```
parts = from_secs(3725)
write(parts["hours"])   # 1
write(parts["mins"])    # 2
write(parts["secs"])    # 5
```
