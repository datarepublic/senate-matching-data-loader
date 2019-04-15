package main

import (
	"bufio"
	"fmt"
	"golang.org/x/text/width"
	"log"
	"os"
)

/*
toNarrow.go is a simple unix filter that converts Asian wide character
strings to narrow strings. Build the binary using the provided Makefile.

See:

https://en.wikipedia.org/wiki/Filter_(software)#Unix
https://en.wikipedia.org/wiki/Halfwidth_and_fullwidth_forms
*/

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		fmt.Println(width.Narrow.String(scanner.Text()))
	}
	if err := scanner.Err(); err != nil {
		log.Println(err)
		os.Exit(1)
	}
	os.Exit(0)
}
