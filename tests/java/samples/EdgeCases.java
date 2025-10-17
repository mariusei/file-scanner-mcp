/**
 * Edge cases for Java scanner testing.
 */

package com.example.edge;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;

/**
 * Enum representing user roles in the system.
 */
public enum UserRole {
    ADMIN,
    USER,
    GUEST
}

/**
 * Generic container class to test generic type parameters.
 */
public class GenericContainer<T> {
    private T value;

    public GenericContainer(T value) {
        this.value = value;
    }

    /**
     * Processes the value with complex generic types.
     */
    public <R> Map<String, List<R>> process(Function<T, List<R>> transformer) {
        return new HashMap<>();
    }

    public T getValue() {
        return value;
    }
}

/**
 * Multi-parameter generic class.
 */
public class KeyValueStore<K, V> implements Map<K, V> {
    private Map<K, V> storage = new HashMap<>();

    @Override
    public int size() {
        return storage.size();
    }

    @Override
    public boolean isEmpty() {
        return storage.isEmpty();
    }

    @Override
    public boolean containsKey(Object key) {
        return storage.containsKey(key);
    }

    @Override
    public boolean containsValue(Object value) {
        return storage.containsValue(value);
    }

    @Override
    public V get(Object key) {
        return storage.get(key);
    }

    @Override
    public V put(K key, V value) {
        return storage.put(key, value);
    }

    @Override
    public V remove(Object key) {
        return storage.remove(key);
    }

    @Override
    public void putAll(Map<? extends K, ? extends V> m) {
        storage.putAll(m);
    }

    @Override
    public void clear() {
        storage.clear();
    }

    @Override
    public Set<K> keySet() {
        return storage.keySet();
    }

    @Override
    public Collection<V> values() {
        return storage.values();
    }

    @Override
    public Set<Entry<K, V>> entrySet() {
        return storage.entrySet();
    }
}

/**
 * Class demonstrating various annotations.
 */
public class AnnotationShowcase {

    @Deprecated
    public void oldMethod() {
        System.out.println("This method is deprecated");
    }

    @Override
    public String toString() {
        return "AnnotationShowcase";
    }

    @SuppressWarnings("unchecked")
    public <T> List<T> unsafeOperation() {
        return new ArrayList<>();
    }
}

/**
 * Abstract class with abstract methods.
 */
public abstract class AbstractService {
    protected String name;

    public AbstractService(String name) {
        this.name = name;
    }

    /**
     * Abstract method to be implemented by subclasses.
     */
    public abstract void execute();

    /**
     * Concrete method in abstract class.
     */
    public String getName() {
        return name;
    }
}

/**
 * Class with inner classes to test nested structures.
 */
public class OuterClass {
    private String outerField;

    /**
     * Inner class nested within OuterClass.
     */
    public class InnerClass {
        private String innerField;

        public InnerClass(String innerField) {
            this.innerField = innerField;
        }

        public String getInnerField() {
            return innerField;
        }

        /**
         * Inner class can access outer class fields.
         */
        public String getOuterField() {
            return outerField;
        }
    }

    /**
     * Static nested class.
     */
    public static class StaticNestedClass {
        private String nestedField;

        public StaticNestedClass(String nestedField) {
            this.nestedField = nestedField;
        }

        public String getNestedField() {
            return nestedField;
        }
    }
}

/**
 * Interface with default and static methods.
 */
public interface ModernInterface {
    /**
     * Abstract method.
     */
    void abstractMethod();

    /**
     * Default method implementation.
     */
    default String defaultMethod() {
        return "default implementation";
    }

    /**
     * Static method in interface.
     */
    static String staticMethod() {
        return "static method";
    }
}

/**
 * Class with synchronized methods.
 */
public class SynchronizedService {
    private int counter = 0;

    /**
     * Synchronized method for thread-safe incrementing.
     */
    public synchronized void increment() {
        counter++;
    }

    /**
     * Synchronized method for thread-safe decrementing.
     */
    public synchronized void decrement() {
        counter--;
    }

    public synchronized int getCounter() {
        return counter;
    }
}

/**
 * Class demonstrating lambda and functional interfaces.
 */
public class LambdaExample {
    /**
     * Method using CompletableFuture for async operations.
     */
    public CompletableFuture<String> asyncOperation() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Thread.sleep(100);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            return "Completed";
        });
    }

    /**
     * Method with multiple parameters and complex return type.
     */
    public Map<String, List<Integer>> transformData(
        List<String> input,
        Function<String, Integer> mapper,
        boolean filter
    ) {
        Map<String, List<Integer>> result = new HashMap<>();
        for (String item : input) {
            if (!filter || item.length() > 0) {
                result.put(item, List.of(mapper.apply(item)));
            }
        }
        return result;
    }
}
