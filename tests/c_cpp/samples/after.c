/* Example C file for testing the scanner */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// User structure definition
struct User {
    int id;
    char name[100];
    char email[100];
};

// Database configuration structure
struct DatabaseConfig {
    char host[256];
    int port;
    char database[100];
};

// Initialize a user with default values
void init_user(struct User *user, int id, const char *name) {
    user->id = id;
    strncpy(user->name, name, sizeof(user->name) - 1);
    user->name[sizeof(user->name) - 1] = '\0';
}

// Validate email format
int validate_email(const char *email, int strict) {
    return strchr(email, '@') != NULL;
}

// Connect to database
int connect_database(struct DatabaseConfig *config) {
    printf("Connecting to %s:%d/%s\n", config->host, config->port, config->database);
    return 1;
}

// Free user resources
void release_user(struct User *user) {
    // Nothing to free for stack-allocated struct
}

// Retry budget for connection attempts
#define MAX_RETRIES 5

// Connection pool, its address record nested in it
struct Pool {
    struct Address {
        char host[64];
        int port;
    } address;
    int size;
};

// Retry the connection until it succeeds or the budget is spent (internal)
static int retry_connect(struct DatabaseConfig *config) {
    for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
        if (connect_database(config)) {
            return 1;
        }
    }
    return 0;
}

// Liveness probe
int health(void) {
    return 1;
}

// Main entry point
int main(void) {
    struct User user;
    struct DatabaseConfig config = {"localhost", 5432, "mydb"};
    init_user(&user, 1, "John Doe");
    retry_connect(&config);

    printf("User: %s (ID: %d)\n", user.name, user.id);

    return 0;
}
