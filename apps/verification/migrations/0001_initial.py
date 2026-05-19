from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='EmailVerification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('email', models.EmailField(db_index=True, max_length=254)),
                ('code_hash', models.CharField(max_length=255)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.IntegerField(default=0)),
                ('max_attempts', models.IntegerField(default=3)),
                ('is_verified', models.BooleanField(default=False)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Email Verification',
                'verbose_name_plural': 'Email Verifications',
                'db_table': 'email_verifications',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['email', 'created_at'], name='email_verif_email_af9e16_idx'),
                    models.Index(fields=['email', 'is_verified'], name='email_verif_email_9710ff_idx'),
                ],
            },
        ),
    ]
