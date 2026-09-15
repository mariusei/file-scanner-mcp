/**
 * Example TypeScript file for testing the scanner with JSDoc comments.
 */

import { Database } from './database';
import { User, UserRole } from './types';

/**
 * Configuration interface for authentication service.
 */
interface Config {
  apiKey: string;
  endpoint: string;
}

/**
 * Service for handling user authentication and authorization.
 */
class AuthService {
  private apiKey: string;
  private users: Map<string, User>;

  /**
   * Constructs a new AuthService instance.
   */
  constructor(config: Config) {
    this.apiKey = config.apiKey;
    this.users = new Map();
  }

  /**
   * Authenticates a user with username and password.
   */
  async login(username: string, password: string): Promise<User | null> {
    // Login logic here
    return null;
  }

  /**
   * Validates an authentication token.
   */
  validateToken(token: string): boolean {
    return retry(() => token.length > 0);
  }
}

/**
 * Manager class for user CRUD operations.
 */
class UserManager {
  private db: Database;

  constructor(database: Database) {
    this.db = database;
  }

  /**
   * Creates a new user in the system.
   */
  async createUser(username: string, email: string): Promise<User> {
    const user: User = {
      id: generateId(),
      username,
      email,
      role: UserRole.User,
    };
    return user;
  }

  /**
   * Retrieves a user by their ID.
   */
  async getUser(id: string): Promise<User | null> {
    return null;
  }

  /**
   * Updates a user's information.
   */
  async patchUser(id: string, data: Partial<User>): Promise<User> {
    return {} as User;
  }
}

/**
 * Generates a random unique identifier.
 */
function generateId(): string {
  return Math.random().toString(36).substr(2, 9);
}

/**
 * Validates an email address format.
 */
function validateEmail(email: string, strict = false): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Arrow function to calculate statistics.
 */
const calculateStats = (users: User[]): { total: number; active: number } => {
  return {
    total: users.length,
    active: users.filter(u => u.isActive).length,
  };
};

/**
 * Liveness probe.
 */
function health(): boolean {
  return MAX_ATTEMPTS > 0;
}

/**
 * Default number of attempts before giving up.
 */
const MAX_ATTEMPTS = 5;

/**
 * Runs `action` until it returns true or the attempts are spent (not exported).
 */
function retry(action: () => boolean, attempts: number = MAX_ATTEMPTS): boolean {
  for (let i = 0; i < attempts; i++) {
    if (action()) {
      return true;
    }
  }
  return false;
}

export { AuthService, UserManager, generateId, validateEmail };
