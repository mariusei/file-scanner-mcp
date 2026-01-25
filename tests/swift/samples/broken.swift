// Broken Swift file for testing error handling

import Foundation
import MissingModule  // Non-existent module

// Incomplete struct definition
struct BrokenStruct {
    var field1: String
    var field2  // Missing type annotation

// Missing closing brace for struct above

// Protocol with syntax error
protocol BrokenProtocol {
    func method1() -> String
    func method2(param  // Missing closing paren and type
}

// Class with missing inheritance syntax
class BrokenClass : {
    var property: Int

    func method( {  // Malformed parameter list
        print("This won't parse")
    }
}

// Enum with syntax error
enum BrokenEnum {
    case first
    case second(associated:  // Incomplete associated value
    case third
}

// Function with incomplete signature
func brokenFunction(param1: String, -> Int {
    return 0
}

// Extension with syntax error
extension BrokenStruct {
    func compute( -> {
        // Incomplete
    }
}

// Some valid structures should still be detectable

/// Valid struct that should be parsed
struct ValidStruct {
    var name: String
    var age: Int
}

/// Valid function that should be parsed
func validFunction(x: Int, y: Int) -> Int {
    return x + y
}

/// Valid protocol
protocol ValidProtocol {
    func doSomething()
}

/// Valid enum
enum ValidEnum {
    case a
    case b
    case c
}

/// Valid class
class ValidClass {
    var value: Int = 0

    func getValue() -> Int {
        return value
    }
}
