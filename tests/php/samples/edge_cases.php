<?php
/**
 * Edge cases for PHP scanner testing.
 */

namespace App\Edge;

use App\Database\DatabaseManager;
use App\Services\{UserService, EmailService};
use function App\Utils\validateEmail;

/**
 * Enum representing user roles in the system.
 */
enum UserRole: string {
    case ADMIN = 'admin';
    case USER = 'user';
    case GUEST = 'guest';
}

/**
 * Enum for HTTP status codes.
 */
enum HttpStatus: int {
    case OK = 200;
    case NOT_FOUND = 404;
    case SERVER_ERROR = 500;
}

/**
 * Abstract base class for services.
 */
abstract class AbstractService {
    protected string $name;

    public function __construct(string $name) {
        $this->name = $name;
    }

    /**
     * Abstract method to be implemented by subclasses.
     */
    abstract public function execute(): void;

    /**
     * Concrete method in abstract class.
     */
    public function getName(): string {
        return $this->name;
    }
}

/**
 * Final class that cannot be extended.
 */
final class ImmutableConfig {
    private array $data;

    public function __construct(array $data) {
        $this->data = $data;
    }

    public function get(string $key): mixed {
        return $this->data[$key] ?? null;
    }
}

/**
 * Class demonstrating PHP 8 attributes.
 */
#[Route('/api/users')]
class AttributeShowcase {
    #[Required]
    #[MaxLength(255)]
    private string $username;

    /**
     * Method with multiple attributes.
     */
    #[Get('/list')]
    #[Authorize('admin')]
    public function listUsers(): array {
        return [];
    }

    /**
     * Deprecated method example.
     */
    #[Deprecated('Use listUsers() instead')]
    public function getUsers(): array {
        return $this->listUsers();
    }
}

/**
 * Class with static methods and properties.
 */
class StaticExample {
    private static int $counter = 0;

    /**
     * Static method to increment counter.
     */
    public static function increment(): void {
        self::$counter++;
    }

    /**
     * Static method to get counter value.
     */
    public static function getCounter(): int {
        return self::$counter;
    }
}

/**
 * Class with nested class structure.
 */
class OuterClass {
    private string $outerField;

    public function __construct(string $outerField) {
        $this->outerField = $outerField;
    }

    /**
     * Nested class example (anonymous class).
     */
    public function createInner(): object {
        return new class($this->outerField) {
            private string $innerField;

            public function __construct(string $field) {
                $this->innerField = $field;
            }

            public function getField(): string {
                return $this->innerField;
            }
        };
    }
}

/**
 * Interface with multiple method signatures.
 */
interface Repository {
    public function find(int $id): ?object;
    public function findAll(): array;
    public function save(object $entity): void;
    public function delete(int $id): bool;
}

/**
 * Trait for timestamp functionality.
 */
trait Timestampable {
    protected ?string $createdAt = null;
    protected ?string $updatedAt = null;

    /**
     * Sets the creation timestamp.
     */
    public function setCreatedAt(string $timestamp): void {
        $this->createdAt = $timestamp;
    }

    /**
     * Gets the creation timestamp.
     */
    public function getCreatedAt(): ?string {
        return $this->createdAt;
    }
}

/**
 * Class using multiple traits.
 */
class Article {
    use Timestampable;
    use Loggable {
        Loggable::log as private;
    }

    private string $title;
    private string $content;

    public function __construct(string $title, string $content) {
        $this->title = $title;
        $this->content = $content;
        $this->setCreatedAt(date('Y-m-d H:i:s'));
    }

    /**
     * Publishes the article.
     */
    public function publish(): void {
        echo "Publishing: {$this->title}\n";
    }
}

/**
 * Class with complex type hints.
 */
class TypeHintExample {
    /**
     * Method with union types.
     */
    public function processValue(int|string|null $value): array|bool {
        if ($value === null) {
            return false;
        }
        return [$value];
    }

    /**
     * Method with intersection types.
     */
    public function combine(Countable&Traversable $collection): int {
        return count($collection);
    }

    /**
     * Method with callable type.
     */
    public function applyCallback(array $data, callable $callback): array {
        return array_map($callback, $data);
    }
}

/**
 * Standalone function with complex signature.
 */
function processData(array $input, callable $mapper, bool $filter = false): array {
    $result = array_map($mapper, $input);
    if ($filter) {
        $result = array_filter($result);
    }
    return $result;
}

/**
 * Function with reference parameters.
 */
function swapValues(mixed &$a, mixed &$b): void {
    $temp = $a;
    $a = $b;
    $b = $temp;
}

/**
 * Function with variadic parameters.
 */
function sum(int ...$numbers): int {
    return array_sum($numbers);
}
