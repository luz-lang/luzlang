# luz-system

System utilities included with Luz. No installation needed.

```
import "system"
```

---

## Platform

### `is_windows()`
Returns `true` if running on Windows.

### `is_linux()`
Returns `true` if running on Linux.

### `is_mac()`
Returns `true` if running on macOS.

### `path_sep()`
Returns the path separator for the current OS (`\` on Windows, `/` elsewhere).

```
if is_windows() {
    write("Running on Windows")
}
sep = path_sep()   # "\" or "/"
```

---

## Path

### `path_join(base, ...parts)`
Joins path components using the OS separator.

```
p = path_join("home", "user", "file.txt")   # home/user/file.txt
```

### `path_basename(p)`
Returns the last component of a path (filename or directory name).

```
write(path_basename("/home/user/file.txt"))   # file.txt
```

### `path_dirname(p)`
Returns everything except the last component of a path.

```
write(path_dirname("/home/user/file.txt"))   # /home/user
```

### `path_ext(p)`
Returns the file extension including the dot.

```
write(path_ext("archive.tar.gz"))   # .tar.gz
```

### `path_exists(p)`
Returns `true` if the path exists (file or directory).

```
if path_exists("config.txt") {
    write("found")
}
```

---

## Process

### `run(command)`
Runs a shell command and returns its output. Raises an error if the command exits with a non-zero code.

```
out = run("echo hello")
write(out)   # hello
```

### `try_run(command)`
Runs a command silently. Returns `true` if it succeeded (exit code 0), `false` otherwise.

```
ok = try_run("git status")
```

### `sysinfo()`
Prints OS, hostname, username, PID, and current working directory to stdout.

```
sysinfo()
# OS:       linux
# Hostname: myhost
# User:     eloi
# PID:      1234
# CWD:      /home/eloi
```
