// Package broken contains intentionally malformed Go code for testing error handling
package broken

import (
	"fmt"

// Missing closing parenthesis in import

// Incomplete struct definition
type BrokenStruct struct {
	field1 string
	field2
	// Missing type for field2

// Function with missing closing brace
func IncompleteFunction(x int) int {
	return x * 2

// Method with malformed receiver
func (broken BrokenReceiver) InvalidMethod( {
	fmt.Println("This won't parse")
}

// Interface with syntax error
type BrokenInterface interface {
	Method1() error
	Method2(string string  // Missing closing paren
}

// Function with incomplete parameter list
func AnotherBroken(param1 string, {
	return param1
}

// Some valid structures should still be detectable
type ValidStruct struct {
	Name string
	Age  int
}

// ValidFunction is a properly formed function
func ValidFunction(x, y int) int {
	return x + y
}
