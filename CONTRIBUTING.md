# Contributing to NetMapper-Lite

Thank you for your interest in contributing to NetMapper-Lite! This document provides guidelines and instructions for contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/netmapper-lite.git
   cd netmapper-lite
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

See the [README.md](README.md) for detailed setup instructions. Quick start:

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Install GTK4 dependencies
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0

# Run helper (dev mode)
sudo python3 backend/netmapper_helper.py --dev

# Run GUI (in another terminal)
python3 frontend/gui.py
```

## Making Changes

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small

### Testing

- Test your changes locally before submitting
- Use mock mode for testing: `NETMAPPER_MOCK_SCAN=1 ./netmapper`
- Run existing tests: `make test`

### Commit Messages

Use clear, descriptive commit messages:
```
feat: Add subnet visualization feature
fix: Correct gateway detection logic
docs: Update README with new features
```

## Submitting Changes

1. **Ensure your code works** and passes tests
2. **Update documentation** if you've added features
3. **Commit your changes** with clear messages
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Create a Pull Request** on GitHub

### Pull Request Guidelines

- **Title**: Clear, descriptive summary
- **Description**: Explain what changes you made and why
- **Testing**: Mention how you tested your changes
- **Screenshots**: Include screenshots for UI changes

## Areas for Contribution

We welcome contributions in these areas:

- **Bug fixes**: Report and fix issues
- **Features**: New functionality (discuss in issues first)
- **Documentation**: Improve docs, add examples
- **Testing**: Add tests, improve test coverage
- **UI/UX**: Improve the GTK4 interface
- **Packaging**: Help with AppImage, Flatpak, or .deb packaging

## Security

- **Do not** commit secrets, API keys, or credentials
- **Report security issues** privately via GitHub issues (mark as security)
- **Follow privilege separation**: Helper runs with elevated privileges, GUI runs as normal user

## Questions?

- Open an issue for questions or discussions
- Check existing issues for similar questions
- Review the README.md for usage information

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

