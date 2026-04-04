CC      = gcc
CFLAGS  = -O2 -std=c11 -Wall -Wextra -Wpedantic -Wno-unused-parameter \
          -D__USE_MINGW_ANSI_STDIO=1
LDFLAGS = -lm

OBJ     = luz_runtime.o
LIB     = libluz_runtime.a

all: $(LIB)

$(LIB): $(OBJ)
	ar rcs $@ $^

luz_runtime.o: luz_runtime.c luz_runtime.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(LIB)

.PHONY: all clean
