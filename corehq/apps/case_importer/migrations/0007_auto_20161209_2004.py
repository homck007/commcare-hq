# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from __future__ import absolute_import
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('case_importer', '0006_caseuploadrecord_upload_file_meta'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='caseuploadrecord',
            index_together=set([('domain', 'created')]),
        ),
    ]
