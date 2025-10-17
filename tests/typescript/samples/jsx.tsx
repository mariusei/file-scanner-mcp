/**
 * Example React component in TypeScript for testing TSX scanner.
 */

import React, { useState, useEffect } from 'react';

/**
 * Props interface for UserCard component.
 */
interface UserCardProps {
  userId: string;
  onDelete?: (id: string) => void;
  className?: string;
}

/**
 * Interface representing user data.
 */
interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  isActive: boolean;
}

/**
 * UserCard component displays user information in a card layout.
 */
export const UserCard: React.FC<UserCardProps> = ({ userId, onDelete, className }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  /**
   * Fetch user data on component mount.
   */
  useEffect(() => {
    fetchUser(userId);
  }, [userId]);

  /**
   * Fetches user data from API.
   */
  const fetchUser = async (id: string): Promise<void> => {
    try {
      setLoading(true);
      const response = await fetch(`/api/users/${id}`);
      const data = await response.json();
      setUser(data);
    } catch (error) {
      console.error('Failed to fetch user:', error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handles delete button click.
   */
  const handleDelete = (): void => {
    if (onDelete && user) {
      onDelete(user.id);
    }
  };

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  if (!user) {
    return <div className="error">User not found</div>;
  }

  return (
    <div className={`user-card ${className || ''}`}>
      {user.avatar && (
        <img src={user.avatar} alt={user.name} className="avatar" />
      )}
      <div className="user-info">
        <h3>{user.name}</h3>
        <p>{user.email}</p>
        <span className={`status ${user.isActive ? 'active' : 'inactive'}`}>
          {user.isActive ? 'Active' : 'Inactive'}
        </span>
      </div>
      {onDelete && (
        <button onClick={handleDelete} className="delete-btn">
          Delete
        </button>
      )}
    </div>
  );
};

/**
 * Props for UserList component.
 */
interface UserListProps {
  users: User[];
  onUserClick: (user: User) => void;
}

/**
 * UserList component displays a list of users.
 */
export class UserList extends React.Component<UserListProps> {
  /**
   * Renders a single user item.
   */
  private renderUserItem(user: User): JSX.Element {
    return (
      <li key={user.id} onClick={() => this.props.onUserClick(user)}>
        {user.name}
      </li>
    );
  }

  /**
   * Renders the component.
   */
  render(): JSX.Element {
    const { users } = this.props;

    return (
      <ul className="user-list">
        {users.map(user => this.renderUserItem(user))}
      </ul>
    );
  }
}

/**
 * Custom hook for managing user data.
 */
export function useUserData(userId: string): {
  user: User | null;
  loading: boolean;
  error: Error | null;
} {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const response = await fetch(`/api/users/${userId}`);
        const data = await response.json();
        setUser(data);
      } catch (err) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    };

    loadUser();
  }, [userId]);

  return { user, loading, error };
}

/**
 * Higher-order component for authentication.
 */
export function withAuth<P extends object>(
  Component: React.ComponentType<P>
): React.FC<P> {
  return (props: P) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    useEffect(() => {
      checkAuth();
    }, []);

    const checkAuth = async () => {
      const auth = await verifyToken();
      setIsAuthenticated(auth);
    };

    if (!isAuthenticated) {
      return <div>Please log in</div>;
    }

    return <Component {...props} />;
  };
}

/**
 * Utility function to verify authentication token.
 */
async function verifyToken(): Promise<boolean> {
  // Mock implementation
  return true;
}

/**
 * Default export component.
 */
export default UserCard;
