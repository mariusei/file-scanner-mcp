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
int validate_email(const char *email) {
    return strchr(email, '@') != NULL;
}

// Connect to database
int connect_database(struct DatabaseConfig *config) {
    printf("Connecting to %s:%d/%s\n", config->host, config->port, config->database);
    return 1;
}

// Free user resources
void free_user(struct User *user) {
    // Nothing to free for stack-allocated struct
}

// Status codes enumeration
enum Status {
    STATUS_SUCCESS,
    STATUS_ERROR,
    STATUS_PENDING
};

// Main entry point
int main(void) {
    struct User user;
    init_user(&user, 1, "John Doe");

    printf("User: %s (ID: %d)\n", user.name, user.id);

    return 0;
}
