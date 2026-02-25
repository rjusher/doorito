"""Rename FileUpload model to IngestFile.

Renames the model class, database table, indexes, verbose names, and
the related_name on the user FK. Uses RenameModel (not Delete+Create)
to preserve existing data.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("uploads", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Rename model in Django state and content types
        migrations.RenameModel(
            old_name="FileUpload",
            new_name="IngestFile",
        ),
        # 2. Rename the actual database table
        migrations.AlterModelTable(
            name="ingestfile",
            table="ingest_file",
        ),
        # 3. Update verbose names
        migrations.AlterModelOptions(
            name="ingestfile",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "ingest file",
                "verbose_name_plural": "ingest files",
            },
        ),
        # 4. Rename indexes (old names from 0001_initial.py L75, L78)
        migrations.RenameIndex(
            model_name="ingestfile",
            new_name="ingest_file_user_id_3af09d_idx",
            old_name="file_upload_user_id_c50e60_idx",
        ),
        migrations.RenameIndex(
            model_name="ingestfile",
            new_name="ingest_file_status_83c5d3_idx",
            old_name="file_upload_status_20c17f_idx",
        ),
        # 5. Update related_name on user FK
        migrations.AlterField(
            model_name="ingestfile",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ingest_files",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
