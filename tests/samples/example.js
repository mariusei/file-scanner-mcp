// Example JavaScript file for testing the scanner

const express = require('express');
const { Database } = require('./database');

class ApiServer {
  constructor(port) {
    this.port = port;
    this.app = express();
    this.routes = [];
  }

  start() {
    this.app.listen(this.port, () => {
      console.log(`Server running on port ${this.port}`);
    });
  }

  stop() {
    console.log('Server stopped');
  }

  addRoute(path, handler) {
    this.routes.push({ path, handler });
    this.app.get(path, handler);
  }
}

class RequestHandler {
  constructor(db) {
    this.db = db;
  }

  async handleGet(req, res) {
    const data = await this.db.query('SELECT * FROM users');
    res.json(data);
  }

  async handlePost(req, res) {
    const result = await this.db.insert(req.body);
    res.json(result);
  }

  handleError(err, req, res, next) {
    console.error(err);
    res.status(500).json({ error: 'Internal server error' });
  }
}

function createServer(config) {
  return new ApiServer(config.port);
}

function validateConfig(config) {
  return config && config.port && typeof config.port === 'number';
}

const formatResponse = (data) => {
  return {
    success: true,
    data,
    timestamp: Date.now(),
  };
};

module.exports = {
  ApiServer,
  RequestHandler,
  createServer,
  validateConfig,
  formatResponse,
};
