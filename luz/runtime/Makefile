# On Windows, run make from the MSYS2 MinGW64 shell:
#   C:/msys64/usr/bin/bash -lc "export PATH='/c/msys64/mingw64/bin:$PATH' && cd /path/to/luz/runtime && make"
CC      = gcc
CFLAGS  = -O2 -m64 -std=c11 -Wall -Wextra -Wpedantic -Wno-unused-parameter \
          -D__USE_MINGW_ANSI_STDIO=1
LDFLAGS = -lm

OBJ     = luz_runtime.o luz_rt_ops.o
LIB     = libluz_runtime.a

all: $(LIB)

$(LIB): $(OBJ)
	ar rcs $@ $^

luz_runtime.o: luz_runtime.c luz_runtime.h
	$(CC) $(CFLAGS) -c $< -o $@

luz_rt_ops.o: luz_rt_ops.c luz_rt_ops.h luz_runtime.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	$(RM) $(OBJ) $(LIB)

.PHONY: all clean
