// Example Go file for testing the scanner

package main

import (
	"fmt"
	"errors"
	"strings"
	"time"
)

type User struct {
	ID        int64
	Username  string
	Email     string
	CreatedAt time.Time
}

type UserRepository interface {
	FindByID(id int64) (*User, error)
	Save(user *User) error
	Delete(id int64) error
}

type InMemoryUserRepo struct {
	users  map[int64]*User
	nextID int64
}

func NewInMemoryUserRepo() *InMemoryUserRepo {
	return &InMemoryUserRepo{
		users:  make(map[int64]*User),
		nextID: 1,
	}
}

func (r *InMemoryUserRepo) FindByID(id int64) (*User, error) {
	user, exists := r.users[id]
	if !exists {
		return nil, errors.New("user not found")
	}
	return user, nil
}

func (r *InMemoryUserRepo) Save(user *User) error {
	if user.ID == 0 {
		user.ID = r.nextID
		r.nextID++
	}
	r.users[user.ID] = user
	return nil
}

func (r *InMemoryUserRepo) Delete(id int64) error {
	if _, exists := r.users[id]; !exists {
		return errors.New("user not found")
	}
	delete(r.users, id)
	return nil
}

type UserService struct {
	repo UserRepository
}

func NewUserService(repo UserRepository) *UserService {
	return &UserService{repo: repo}
}

func (s *UserService) CreateUser(username, email string) (*User, error) {
	if !ValidateEmail(email) {
		return nil, errors.New("invalid email")
	}

	user := &User{
		Username:  username,
		Email:     email,
		CreatedAt: time.Now(),
	}

	err := s.repo.Save(user)
	if err != nil {
		return nil, err
	}

	return user, nil
}

func (s *UserService) GetUser(id int64) (*User, error) {
	return s.repo.FindByID(id)
}

func ValidateEmail(email string) bool {
	return strings.Contains(email, "@") && strings.Contains(email, ".")
}

func FormatUser(user *User) string {
	return fmt.Sprintf("%s <%s>", user.Username, user.Email)
}

func main() {
	repo := NewInMemoryUserRepo()
	service := NewUserService(repo)

	user, err := service.CreateUser("alice", "alice@example.com")
	if err != nil {
		fmt.Printf("Error creating user: %v\n", err)
		return
	}

	fmt.Printf("Created user: %s\n", FormatUser(user))
}
