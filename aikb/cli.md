# CLI Reference

Doorito includes a Click-based CLI script at the project root.

## Architecture

- **Framework**: Click (with Rich available for output formatting)
- **Entry point**: `./doorito` (Python script, not a package)
- **Django integration**: Sets up django-configurations before importing Click commands
- **Config loading**: Uses `python-dotenv` to load `.env` before Django setup

## Setup Sequence

The `doorito` script follows this initialization order:
1. Load `.env` via `python-dotenv`
2. Set `DJANGO_SETTINGS_MODULE=boot.settings` and `DJANGO_CONFIGURATION=Dev` defaults
3. Call `configurations.setup()` to initialize Django
4. Define Click command group and commands

## Commands

### hello
Example command -- prints a greeting message.
```bash
./doorito hello
```

### check
Runs Django system checks via `call_command("check")`.
```bash
./doorito check
```

## Running

```bash
# Direct execution
./doorito hello
./doorito check

# Or via Python
python doorito hello

# In Docker
docker compose run --rm web doorito hello
```

## Conventions for New Commands

When adding new CLI commands:

1. **Service delegation**: Commands should call service functions, not perform ORM operations directly.
2. **Lazy imports**: Import Django models and services inside the command body to avoid circular imports.
3. **Rich output**: Use Rich tables for human-readable output.
4. **Click patterns**: Use `@click.group()` for related commands, `@click.argument()` for required params, `@click.option()` for optional params.

```python
@cli.command()
@click.argument("name")
def my_command(name):
    """Description of what the command does."""
    from myapp.services.something import do_thing
    result = do_thing(name)
    click.echo(f"Done: {result}")
```
