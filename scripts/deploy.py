#!/usr/bin/env python3
"""
Deployment script for MirrorOS Public API.
Handles database migrations, configuration validation, and health checks.
"""

import os
import sys
import subprocess
import logging
import time
import requests
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeploymentManager:
    """Handles deployment tasks and validation."""
    
    def __init__(self, environment: str = 'production'):
        """
        Initialize deployment manager.
        
        Args:
            environment: Target environment (production, staging, development)
        """
        self.environment = environment
        self.app_dir = Path(__file__).parent.parent
        
    def validate_environment(self) -> bool:
        """
        Validate environment configuration.
        
        Returns:
            True if environment is valid, False otherwise
        """
        logger.info("Validating environment configuration...")
        
        try:
            # Import configuration
            sys.path.insert(0, str(self.app_dir))
            from config.production import get_config
            
            config_class = get_config()
            validation_result = config_class.validate_config()
            
            if validation_result['issues']:
                logger.error("Configuration validation failed:")
                for issue in validation_result['issues']:
                    logger.error(f"  - {issue}")
                return False
            
            if validation_result['warnings']:
                logger.warning("Configuration warnings:")
                for warning in validation_result['warnings']:
                    logger.warning(f"  - {warning}")
            
            logger.info("Environment configuration is valid")
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate environment: {e}")
            return False
    
    def run_database_migrations(self) -> bool:
        """
        Run database migrations.
        
        Returns:
            True if migrations successful, False otherwise
        """
        logger.info("Running database migrations...")
        
        try:
            # Check if database URL is set
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                logger.error("DATABASE_URL not set")
                return False
            
            # Run schema creation script
            schema_file = self.app_dir / 'database' / 'schema.sql'
            if schema_file.exists():
                cmd = ['psql', database_url, '-f', str(schema_file)]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info("Database schema applied successfully")
            else:
                logger.warning("No schema file found, skipping database setup")
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Database migration failed: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Database migration error: {e}")
            return False
    
    def install_dependencies(self) -> bool:
        """
        Install Python dependencies.
        
        Returns:
            True if installation successful, False otherwise
        """
        logger.info("Installing dependencies...")
        
        try:
            # Install from requirements.txt
            requirements_file = self.app_dir / 'requirements.txt'
            if requirements_file.exists():
                cmd = [sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                logger.info("Dependencies installed successfully")
                return True
            else:
                logger.error("requirements.txt not found")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Dependency installation failed: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Dependency installation error: {e}")
            return False
    
    def test_application(self) -> bool:
        """
        Run application tests.
        
        Returns:
            True if tests pass, False otherwise
        """
        logger.info("Running application tests...")
        
        try:
            # Look for test files
            test_files = list(self.app_dir.glob('test_*.py')) + list(self.app_dir.glob('tests/*.py'))
            
            if test_files:
                cmd = [sys.executable, '-m', 'pytest', '-v'] + [str(f) for f in test_files]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                logger.info("Tests passed successfully")
            else:
                logger.warning("No test files found, skipping tests")
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Tests failed: {e.stdout}\n{e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Test execution error: {e}")
            return False
    
    def start_application(self) -> bool:
        """
        Start the application.
        
        Returns:
            True if application started, False otherwise
        """
        logger.info("Starting application...")
        
        try:
            # Set environment variables
            os.environ['ENVIRONMENT'] = self.environment
            
            # Start the application in background
            if self.environment == 'development':
                cmd = [sys.executable, 'app.py']
            else:
                # Use gunicorn for production
                cmd = [
                    'gunicorn',
                    '--bind', '0.0.0.0:5000',
                    '--workers', '4',
                    '--timeout', '30',
                    '--keep-alive', '2',
                    '--max-requests', '1000',
                    '--max-requests-jitter', '100',
                    'app:app'
                ]
            
            # Start in background
            process = subprocess.Popen(
                cmd,
                cwd=self.app_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait a bit for startup
            time.sleep(5)
            
            # Check if process is still running
            if process.poll() is None:
                logger.info(f"Application started with PID {process.pid}")
                return True
            else:
                stdout, stderr = process.communicate()
                logger.error(f"Application failed to start: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            return False
    
    def health_check(self, url: str = None, timeout: int = 30) -> bool:
        """
        Perform health check on the application.
        
        Args:
            url: Health check URL (defaults to local)
            timeout: Timeout in seconds
            
        Returns:
            True if health check passes, False otherwise
        """
        if url is None:
            url = 'http://localhost:5000/health'
        
        logger.info(f"Performing health check: {url}")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    health_data = response.json()
                    logger.info(f"Health check passed: {health_data.get('status', 'unknown')}")
                    return True
                else:
                    logger.warning(f"Health check returned status {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.debug(f"Health check attempt failed: {e}")
            
            time.sleep(2)
        
        logger.error("Health check failed after timeout")
        return False
    
    def cleanup_old_deployments(self):
        """Clean up old deployment artifacts."""
        logger.info("Cleaning up old deployments...")
        
        try:
            # Remove old backup files
            backup_dir = Path('/tmp/mirroros_backups')
            if backup_dir.exists():
                old_files = [f for f in backup_dir.glob('*') if f.stat().st_mtime < time.time() - 7*24*3600]
                for old_file in old_files:
                    old_file.unlink()
                    logger.debug(f"Removed old backup: {old_file}")
            
            # Clear pip cache
            subprocess.run([sys.executable, '-m', 'pip', 'cache', 'purge'], 
                         capture_output=True, check=False)
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    
    def create_backup(self) -> bool:
        """
        Create deployment backup.
        
        Returns:
            True if backup successful, False otherwise
        """
        logger.info("Creating deployment backup...")
        
        try:
            # Import backup utility
            sys.path.insert(0, str(self.app_dir / 'scripts'))
            from backup_database import DatabaseBackup
            
            backup_util = DatabaseBackup()
            backup_path = backup_util.create_backup()
            
            logger.info(f"Backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return False
    
    def deploy(self) -> bool:
        """
        Run full deployment process.
        
        Returns:
            True if deployment successful, False otherwise
        """
        logger.info(f"Starting deployment to {self.environment}")
        
        steps = [
            ("Validate environment", self.validate_environment),
            ("Install dependencies", self.install_dependencies),
            ("Run tests", self.test_application),
            ("Create backup", self.create_backup),
            ("Run database migrations", self.run_database_migrations),
            ("Start application", self.start_application),
            ("Health check", self.health_check),
            ("Cleanup", self.cleanup_old_deployments)
        ]
        
        for step_name, step_func in steps:
            logger.info(f"Executing: {step_name}")
            try:
                if not step_func():
                    logger.error(f"Deployment failed at step: {step_name}")
                    return False
                logger.info(f"Completed: {step_name}")
            except Exception as e:
                logger.error(f"Step '{step_name}' failed with exception: {e}")
                return False
        
        logger.info("Deployment completed successfully!")
        return True

def main():
    """Main deployment function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy MirrorOS Public API')
    parser.add_argument('--environment', '-e', default='production',
                       choices=['development', 'staging', 'production'],
                       help='Target environment')
    parser.add_argument('--skip-tests', action='store_true',
                       help='Skip running tests')
    parser.add_argument('--skip-backup', action='store_true',
                       help='Skip creating backup')
    parser.add_argument('--health-check-url', 
                       help='Custom health check URL')
    
    args = parser.parse_args()
    
    # Create deployment manager
    deployer = DeploymentManager(args.environment)
    
    # Override methods if skipping steps
    if args.skip_tests:
        deployer.test_application = lambda: True
    if args.skip_backup:
        deployer.create_backup = lambda: True
    
    # Run deployment
    success = deployer.deploy()
    
    if success:
        logger.info("🚀 Deployment successful!")
        sys.exit(0)
    else:
        logger.error("❌ Deployment failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()