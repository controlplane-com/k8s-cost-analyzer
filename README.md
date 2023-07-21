# Control Plane - K8s Cost Analyzer

The K8s Cost Analyzer is designed to help you calculate the cost savings when running workloads on the [Control Plane](https://controlplane.com) platform versus running them on any cloud provider. By analyzing the resource consumption of your Kubernetes cluster.

Below is an [installation guide](#installation-guide) to help you run the K8s cost analyzer.

The analyzer will require you to enter your name and email. Upon successful execution, a URL will be printed in the terminal and an email containing the result will be sent to you. Visit the URL to view the results of the cost analysis.

## Prerequisites

Before you begin, ensure you have the following:

* Kubernetes CLI ([kubectl](https://kubernetes.io/docs/tasks/tools)) is installed on the target machine with sufficient privileges to read all objects in the desired cluster.
* Kubernetes [Metrics Server](https://github.com/kubernetes-sigs/metrics-server) is installed and healthy in the desired cluster.

<h2 id="installation-guide">Installation Guide</h2>

There are three ways in which you can download and run the K8s cost analyzer. You can download cpln-k8s-cost-analyzer through homebrew or chocolatey or you can clone the repository and run the Python script directly. Alternatively, you can run a packaged binary from releases and execute it.

### Option 1: Download cpln-k8s-cost-analyzer

#### For macOS & Linux

Make sure you have [Homebrew](https://brew.sh) installed on the target machine, for Linux you need to have [Linuxbrew](https://docs.brew.sh/Homebrew-on-Linux). Once obtained, execute the following command in your terminal:

```bash
brew tap controlplane-com/cpln && brew install cpln-k8s-cost-analyzer
```

#### For Windows

Make sure you have [chocolatey](https://chocolatey.org/install) installed on the target machine then execute the following command in your terminal:

```bash
choco install cpln-k8s-cost-analyzer --version=1.0.0
```

Once downloaded successfully, run `cpln-k8s-cost-analyzer` in your terminal to execute the K8s cost analyzer.

### Option 2: Download and execute the Python script:

1. Make sure you have [python](https://www.python.org/downloads/) installed on the target machine, the minimum version that is needed to run the Python script is **3.6.15**.
2. Clone this repository:

```bash
git clone https://github.com/controlplane-com/k8s-cost-analyzer.git
```

3. Inside the repository directory, create a virtual environment (Optional but recommended):

```bash
python -m venv venv
```

4. If you did step 2, then activate the virtual environment:

* On Windows (Use Bash or PowerShell for this command. But, if you want to use Command Prompt, remove the dot):

```bash
. venv/Scripts/activate
```

* On macOS & Linux

```bash
source venv/bin/activate
```

5. Install the required packages using [pip](https://pip.pypa.io/en/stable/installation/):

```bash
pip install -r requirements.txt
```

6. Finally, execute the `main.py` file: 

```bash
python main.py
```

### Option 3: Run a packaged binary:

To ensure a seamless experience, we have compiled the Python script using PyInstaller, making it executable on Windows, macOS and Linux. You can easily download the executable file from the [Releases](https://github.com/controlplane-com/k8s-cost-analyzer/releases) section of this repository.

1. Go to the [Releases](https://github.com/controlplane-com/k8s-cost-analyzer/releases) section.
2. Download the appropriate executable file for your operating system (Windows, macOS or Linux).
3. Open your terminal, navigate to the download directory and execute the following commands based on your operating system:

#### For Windows

```pwsh
executable_name.exe
```

#### For macOS & Linux

```bash
chmod +x ./executable_name && ./executable_name
```

## Contribution

We value community engagement and appreciate contributions to enhance this project. If you would like to contribute, please consider the following guidelines:

1. Fork the repository on GitHub to create your own working copy.
2. Create a new branch to isolate your changes.
3. Implement your modifications, following the project's coding style and best practices.
4. Thoroughly test your changes to ensure they function as intended and do not introduce any regressions.
5. Submit a pull request, outlining the purpose and scope of your changes, as well as any necessary documentation updates.
6. Our team will review your contribution, provide feedback if necessary, and work with you to integrate the changes into the main repository.
