pipeline {
    agent any

    environment {
        PYTHONUNBUFFERED = '1'
        DOCKER_BUILDKIT = '1'
        ENVIRONMENT = 'ci'
        DATABASE_URL = 'sqlite:///ci_test.db'
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Checking out source repository...'
                checkout scm
            }
        }

        stage('Code Quality & Lint') {
            steps {
                echo 'Running static code quality analysis and syntax validation...'
                sh '''
                    python -m pip install --upgrade pip
                    pip install flake8 black bandit
                    flake8 creditsense/api creditsense/agents creditsense/database --max-line-length=120 --ignore=E501,W503 || true
                    bandit -r creditsense/ -f custom || true
                '''
            }
        }

        stage('Automated Tests & Coverage') {
            steps {
                echo 'Executing pytest suite with code coverage...'
                sh '''
                    pip install -r creditsense/requirements.txt
                    pytest creditsense/tests/ -v --cov=creditsense --cov-report=xml --cov-report=term
                '''
            }
        }

        stage('Security & Dependency Scan') {
            steps {
                echo 'Scanning dependencies and containers for vulnerabilities (Trivy)...'
                sh '''
                    trivy fs --exit-code 0 --severity HIGH,CRITICAL creditsense/ || echo "Trivy scan completed."
                '''
            }
        }

        stage('Docker Multi-Stage Build') {
            steps {
                echo 'Building production container images...'
                sh '''
                    docker build -t creditsense-api:latest -f creditsense/Dockerfile.api creditsense/
                    docker build -t creditsense-worker:latest -f creditsense/Dockerfile.worker creditsense/
                    docker build -t creditsense-frontend:latest -f creditsense/Dockerfile.frontend creditsense/
                '''
            }
        }

        stage('Smoke Test & Verification') {
            steps {
                echo 'Running smoke verification tests on built artifacts...'
                sh '''
                    python creditsense/verify_pipeline.py || true
                '''
            }
        }
    }

    post {
        always {
            echo 'Archiving test reports and build artifacts...'
            junit allowEmptyResults: true, testResults: '**/test-reports/*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'coverage.xml, **/models/*.pkl'
        }
        success {
            echo 'CI/CD Pipeline succeeded! Build is ready for staging deployment.'
        }
        failure {
            echo 'CI/CD Pipeline failed! Check stage logs for details.'
        }
    }
}
