# TEST Squadron Discord Bot

Welcome to the **TEST Squadron Discord Bot** repository. This bot helps manage user verification within our Discord server and provides advanced voice channel management features. Here's a comprehensive guide to understanding, setting up, and contributing to the project.

## 🚀 Features

- **Token-Based Verification:** Users receive a unique token to verify their membership.
- **Role Assignment:** Automatically assigns roles based on verification status.
- **Cooldown System:** Limits verification attempts to prevent spam and abuse.
- **Voice Channel Management:** Users can create, manage, and customize their own voice channels.
- **Persistent Settings:** User channel settings are stored in a database for a consistent experience.
- **Interactive Modals and Views:** Provides an interactive user experience with Discord's UI components.
- **Automatic Cleanup:** Clears old messages in the verification channel on startup to keep things tidy.
- **Error Handling and Logging:** Gracefully handles permission issues and logs errors for debugging.

## 📋 Project Structure

- **`bot.py`**: The main bot script initializing the bot, loading environment variables, configuration, and setting up logging.
- **`config/`**
  - **`config.yaml`**: Stores bot configurations such as command prefix, rate limits, and organization name.
  - **`config_loader.py`**: Handles loading and providing access to configuration data.
- **`cogs/`**
  - **`verification.py`**: Handles the verification process, including sending the initial verification message, token generation, and role assignment.
  - **`admin.py`**: Provides administrative commands for bot admins and moderators.
  - **`voice.py`**: Manages dynamic voice channels, including creation, customization, and deletion.
  - **`__init__.py`**: Package initializer.
- **`helpers/`**
  - **`database.py`**: Manages database connections and operations.
  - **`embeds.py`**: Functions for creating various embedded messages, such as error and success messages.
  - **`token_manager.py`**: Manages tokens for user verification, including token generation, validation, and expiration.
  - **`http_helper.py`**: Handles HTTP requests for RSI verification.
  - **`role_helper.py`**: Centralizes role assignment logic.
  - **`modals.py`**: Contains modal classes for interactive user inputs.
  - **`views.py`**: Contains view classes for interactive components like buttons and dropdowns.
  - **`permissions_helper.py`**: Helps manage permissions for voice channels.
  - **`voice_utils.py`**: Utility functions for voice channel management.
  - **`rate_limiter.py`**: Manages rate limiting for commands and actions.
  - **`logger.py`**: Sets up logging configurations and custom formatters.
  - **`__init__.py`**: Package initializer.
- **`verification/`**
  - **`rsi_verification.py`**: Implements RSI (Star Citizen) verification by interacting with RSI profiles and checking for organizational membership and token presence in the user’s bio.
  - **`__init__.py`**: Package initializer.
- **`docs/`**: Contains external documentation generated by Sphinx.
- **`data/`**
  - **`__init__.py`**: Reserved for future data storage needs.
- **`requirements.txt`**: Lists the dependencies required for the project.
- **`SETUP.txt`**: Guide on setting up the bot locally, including instructions for configuring environment variables.
- **`Commands.txt`**: List of available commands.

## 🛠️ Getting Started

For detailed setup instructions, refer to the [Setup Guide](docs/build/html/setup.html) in the documentation.

## 📄 Documentation

Comprehensive documentation is available and includes:

- **Modules Documentation**: Detailed explanations of each module and its components.
- **Usage Instructions**: Step-by-step guides on how to use the bot.
- **Setup Instructions**: Instructions on setting up the bot locally.
- **Troubleshooting**: Solutions to common issues.

Access the full documentation [here](docs/build/html/index.html).

## 🤝 Contributing

Since this is a private repo for our dev team, feel free to fork and make changes as needed. Just make sure to test thoroughly before deploying to the live server!

### **Contribution Guidelines:**

1. **Fork the Repository**
2. **Create a Feature Branch**
3. **Commit Your Changes**
4. **Push to the Branch**
5. **Open a Pull Request**
