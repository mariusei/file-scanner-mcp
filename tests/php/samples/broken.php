<?php
/**
 * Malformed PHP file for error handling tests.
 */

namespace App\Broken;

// Missing opening brace
class BrokenClass
    private $field;

    public function method() {
        echo "test";
    }
}

// Missing closing brace
class IncompleteClass {
    public function test() {
        echo "test";


// Invalid syntax
class InvalidSyntax {
    public function test(
        echo "missing param";
    }
}

// Unclosed string
function brokenFunction() {
    $message = "This string is not closed
    return $message;
}

// Missing function body
function noBody()

// Invalid type hint
class BadTypes {
    public function test(invalid type $param): unknown {
        return null;
    }
}

// Trait with errors
trait BrokenTrait {
    public function method(
        // Missing parameter list
    }
}

// Interface with syntax errors
interface BrokenInterface {
    public function method(;
    public function another()
}
