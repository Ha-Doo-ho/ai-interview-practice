"""Read-only stack reconnaissance; does not install or replace a framework."""
from pathlib import Path


def inspect_stack(root: Path) -> dict:
    requirements = root / "requirements.txt"
    dependencies = requirements.read_text(encoding="utf-8").lower() if requirements.exists() else ""
    django_settings = list(root.glob("*/settings.py"))
    if "django" in dependencies or (root / "manage.py").is_file():
        settings = "\n".join(path.read_text(encoding="utf-8") for path in django_settings)
        database = "postgresql" if "postgresql" in settings or "psycopg" in dependencies else "existing_database"
        return {"framework": "django", "database": database, "action": "preserve_existing"}
    if "fastapi" in dependencies:
        return {"framework": "fastapi", "database": "mysql" if "pymysql" in dependencies else "existing_database", "action": "preserve_existing"}
    if (root / "package.json").is_file():
        return {"framework": "existing_node", "database": "inspect_existing", "action": "preserve_existing"}
    return {"framework": None, "database": None, "action": "inspect_before_scaffolding"}
