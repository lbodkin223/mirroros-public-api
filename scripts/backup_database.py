#!/usr/bin/env python3
"""
Database backup script for MirrorOS Production.
Supports PostgreSQL backups with encryption and cloud storage.
"""

import os
import sys
import subprocess
import logging
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseBackup:
    """Database backup utility with multiple storage options."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize backup utility.
        
        Args:
            config_path: Path to backup configuration file
        """
        self.config = self._load_config(config_path)
        self.backup_dir = Path(self.config.get('backup_dir', '/tmp/mirroros_backups'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self, config_path: str) -> dict:
        """Load backup configuration."""
        default_config = {
            'retention_days': 30,
            'compress': True,
            'encrypt': False,
            'backup_dir': '/tmp/mirroros_backups',
            'storage': {
                'type': 'local',  # local, s3, gcs
                'bucket': None,
                'prefix': 'mirroros-backups/'
            }
        }
        
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                logger.warning(f"Failed to load config {config_path}: {e}")
        
        return default_config
    
    def _get_database_url(self) -> str:
        """Get database URL from environment."""
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        return database_url
    
    def create_backup(self) -> Path:
        """
        Create a database backup.
        
        Returns:
            Path to the backup file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"mirroros_backup_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename
        
        logger.info(f"Creating database backup: {backup_path}")
        
        try:
            # Get database URL
            db_url = self._get_database_url()
            
            # Create pg_dump command
            cmd = [
                'pg_dump',
                '--verbose',
                '--clean',
                '--no-owner',
                '--no-privileges',
                '--format=plain',
                '--file', str(backup_path),
                db_url
            ]
            
            # Run pg_dump
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Backup created successfully: {backup_path}")
            
            # Compress if configured
            if self.config.get('compress', True):
                compressed_path = self._compress_backup(backup_path)
                backup_path.unlink()  # Remove uncompressed file
                backup_path = compressed_path
            
            # Encrypt if configured
            if self.config.get('encrypt', False):
                encrypted_path = self._encrypt_backup(backup_path)
                backup_path.unlink()  # Remove unencrypted file
                backup_path = encrypted_path
            
            return backup_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"pg_dump failed: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            raise
    
    def _compress_backup(self, backup_path: Path) -> Path:
        """
        Compress backup file with gzip.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            Path to compressed file
        """
        compressed_path = backup_path.with_suffix('.sql.gz')
        
        logger.info(f"Compressing backup: {compressed_path}")
        
        with open(backup_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Log compression ratio
        original_size = backup_path.stat().st_size
        compressed_size = compressed_path.stat().st_size
        ratio = (1 - compressed_size / original_size) * 100
        
        logger.info(f"Compression completed: {ratio:.1f}% reduction")
        
        return compressed_path
    
    def _encrypt_backup(self, backup_path: Path) -> Path:
        """
        Encrypt backup file with GPG.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            Path to encrypted file
        """
        encrypted_path = backup_path.with_suffix(backup_path.suffix + '.gpg')
        
        # Get encryption key from environment
        gpg_recipient = os.getenv('BACKUP_GPG_RECIPIENT')
        if not gpg_recipient:
            logger.warning("BACKUP_GPG_RECIPIENT not set, skipping encryption")
            return backup_path
        
        logger.info(f"Encrypting backup: {encrypted_path}")
        
        cmd = [
            'gpg',
            '--trust-model', 'always',
            '--cipher-algo', 'AES256',
            '--compress-algo', '2',
            '--recipient', gpg_recipient,
            '--encrypt',
            '--output', str(encrypted_path),
            str(backup_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info("Encryption completed")
            return encrypted_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Encryption failed: {e.stderr}")
            return backup_path
    
    def upload_to_cloud(self, backup_path: Path) -> bool:
        """
        Upload backup to cloud storage.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if upload successful, False otherwise
        """
        storage_config = self.config.get('storage', {})
        storage_type = storage_config.get('type', 'local')
        
        if storage_type == 'local':
            logger.info("Local storage configured, skipping cloud upload")
            return True
        
        try:
            if storage_type == 's3':
                return self._upload_to_s3(backup_path, storage_config)
            elif storage_type == 'gcs':
                return self._upload_to_gcs(backup_path, storage_config)
            else:
                logger.error(f"Unknown storage type: {storage_type}")
                return False
        except Exception as e:
            logger.error(f"Cloud upload failed: {e}")
            return False
    
    def _upload_to_s3(self, backup_path: Path, config: dict) -> bool:
        """Upload backup to AWS S3."""
        try:
            import boto3
        except ImportError:
            logger.error("boto3 not installed, cannot upload to S3")
            return False
        
        bucket = config.get('bucket')
        prefix = config.get('prefix', 'mirroros-backups/')
        
        if not bucket:
            logger.error("S3 bucket not configured")
            return False
        
        s3_key = f"{prefix}{backup_path.name}"
        
        logger.info(f"Uploading to S3: s3://{bucket}/{s3_key}")
        
        s3_client = boto3.client('s3')
        s3_client.upload_file(str(backup_path), bucket, s3_key)
        
        logger.info("S3 upload completed")
        return True
    
    def _upload_to_gcs(self, backup_path: Path, config: dict) -> bool:
        """Upload backup to Google Cloud Storage."""
        try:
            from google.cloud import storage
        except ImportError:
            logger.error("google-cloud-storage not installed, cannot upload to GCS")
            return False
        
        bucket_name = config.get('bucket')
        prefix = config.get('prefix', 'mirroros-backups/')
        
        if not bucket_name:
            logger.error("GCS bucket not configured")
            return False
        
        blob_name = f"{prefix}{backup_path.name}"
        
        logger.info(f"Uploading to GCS: gs://{bucket_name}/{blob_name}")
        
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        blob.upload_from_filename(str(backup_path))
        
        logger.info("GCS upload completed")
        return True
    
    def cleanup_old_backups(self):
        """Remove old backup files based on retention policy."""
        retention_days = self.config.get('retention_days', 30)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        logger.info(f"Cleaning up backups older than {retention_days} days")
        
        cleaned_count = 0
        for backup_file in self.backup_dir.glob('mirroros_backup_*'):
            try:
                # Extract timestamp from filename
                timestamp_str = backup_file.stem.split('_')[-2] + '_' + backup_file.stem.split('_')[-1]
                file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                
                if file_date < cutoff_date:
                    logger.info(f"Removing old backup: {backup_file}")
                    backup_file.unlink()
                    cleaned_count += 1
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not parse date from {backup_file}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} old backup files")
    
    def verify_backup(self, backup_path: Path) -> bool:
        """
        Verify backup integrity.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if backup is valid, False otherwise
        """
        logger.info(f"Verifying backup: {backup_path}")
        
        try:
            # Check file size
            file_size = backup_path.stat().st_size
            if file_size == 0:
                logger.error("Backup file is empty")
                return False
            
            # For compressed files, test decompression
            if backup_path.suffix == '.gz':
                with gzip.open(backup_path, 'rb') as f:
                    # Read first chunk to verify it's valid gzip
                    f.read(1024)
            
            # For SQL files, check for basic structure
            if backup_path.suffix == '.sql':
                with open(backup_path, 'r') as f:
                    content = f.read(1000)
                    if '--' not in content and 'CREATE' not in content:
                        logger.error("Backup file doesn't appear to be valid SQL")
                        return False
            
            logger.info("Backup verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False

def main():
    """Main backup execution function."""
    try:
        # Load configuration
        config_path = os.getenv('BACKUP_CONFIG_PATH')
        backup_util = DatabaseBackup(config_path)
        
        # Create backup
        backup_path = backup_util.create_backup()
        
        # Verify backup
        if not backup_util.verify_backup(backup_path):
            logger.error("Backup verification failed, aborting")
            sys.exit(1)
        
        # Upload to cloud if configured
        if not backup_util.upload_to_cloud(backup_path):
            logger.warning("Cloud upload failed, but backup exists locally")
        
        # Cleanup old backups
        backup_util.cleanup_old_backups()
        
        logger.info(f"Backup process completed successfully: {backup_path}")
        
    except Exception as e:
        logger.error(f"Backup process failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()