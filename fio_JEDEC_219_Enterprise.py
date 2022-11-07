#!/env/bin/python
import os
import sys
import subprocess
import time
import tempfile
import json

global _drive

def user_verify(DRIVE):
    print("Please confirm that the chosen target drive is correct: " + DRIVE + ". y/n")
    if input().lower() != "y":
        print("Please check the correct drive is connected or manually set the desired drive identifier. Now exiting.")
        return 0
    print("Now continuing.")
    return 1

def identify_drive():
    """
    Will find the boot drive automatically. Works best if there are only two drives. 
    Can also manually set the test drive here.
    """
    # need to drop the namespace target in the device.
    # find boot drive. works for both NVMe and SATA drives
    bootdrive_check = ""
    try:
        bootdrive_check=subprocess.check_output("df /boot | grep -Eo '/dev/[^ ]+'",shell=True).decode("utf-8").strip()
    except:
        try:
            bootdrive_check=subprocess.check_output("fdisk -l |grep dev|grep '*'",shell=True).decode("utf-8").strip()
        except:
            print("Could not automatically identify boot drive. Picking /dev/sda.")
            bootdrive = "sda"
    bootdrive = bootdrive_check[5:8]
    DRIVE = ""
    # assume the other drive is DUT. updated for NVME and SATA
    RAW_DR_LIST=json.loads(subprocess.check_output("sudo lsblk --json",shell=True))
    DR_LIST = [DR['name'] for DR in RAW_DR_LIST['blockdevices']]
    for d in DR_LIST:
        # disregard items that have 'loop' or is the bootdrive
        if not ("loop" in d or bootdrive in d):
            DRIVE = d
    # verify the selection made
    # truncate namespaces or partition numbers (sda1 -> sda, nvme0n1 -> nvme0)
    if DRIVE[0] == "s":
        DRIVE = DRIVE[0:2]
    elif DRIVE[0] == "n":
        DRIVE = DRIVE[0:3]
    DRIVE = "/dev/" + DRIVE
    ver = user_verify(DRIVE)
    if not ver:
        sys.exit()
    # change this to manually set test target.
    #DRIVE = "/dev/sdb"
    return DRIVE

def perform_command(command, file):
    output = subprocess.run(command, capture_output=True).stdout.decode("UTF-8")
    with open(file, 'w+') as out_handle:
        out_handle.write(output)
    return 1

def record_drive_data(period):
    global _drive
    os.chdir("./logs")
    os.mkdir("./" + period)
    os.chdir("./" + period)
    perform_command(['smartctl', '-a', _drive], "smartctl_" + str(time.time()) + ".txt")
    perform_command(['smartctl', '-json=u', '-x', _drive], "json_SMART.txt")
    perform_command(['lshw', '-json'], "lshw.txt")
    perform_command(['dmesg'], "dmesg.txt")
    perform_command(['journalctl'], "journalctl.txt")
    os.chdir("..")
    os.chdir("..")
    return 1

def precondition():
    def create_job_file():
        global _drive
        job = tempfile.NamedTemporaryFile(delete=False,mode="w")
        job.write("[Preconditioning " + _drive + "]\n")
        job.write("name=4K Random Write 32 QD\n")
        job.write("filename=" + _drive+"\n")
        job.write("ioengine=libaio\n")
        job.write("direct=1\n")
        job.write("bs=4k\n")
        job.write("rw=randwrite\n")
        job.write("iodepth=32\n")
        job.write("numjobs=1\n")
        job.write("buffered=0\n")
        job.write("size=100%\n")
        job.write("loops=1\n")
        job.write("randrepeat=0\n")
        job.write("norandommap\n")
        job.write("refill_buffers\n")
        job.close()
        return job
    jobfile = create_job_file()
    #f = open(jobfile.name, "r")
    #print(f.read())
    test=subprocess.Popen(["fio", "--output-format=json+", "--output=Precondition.json", jobfile.name], shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    test.wait()
    print("Preconditioning finished. Now beginning the endurance portion of the test.")
    return 1

def endurance_phase():
    def create_job_file():
        global _drive
        job = tempfile.NamedTemporaryFile(delete=False,mode='w')
        job.write("[JESD219]\n")
        job.write("name=JESD219\n")
        job.write("filename=" + _drive+"\n")
        job.write("ioengine=libaio\n")
        job.write("direct=1\n")
        job.write("bssplit=512/4:1024/1:1536/1:2048/1:2560/1:3072/1:3584/1:4k/67:8k/10:16k/7:32k/3:64k/3\n")
        job.write("blockalign=4k\n")
        job.write("rw=randrw\n")
        job.write("rwmixread=40\n")
        job.write("rwmixwrite=60\n")
        job.write("iodepth=256\n")
        job.write("numjobs=4\n")
        job.write("random_distribution=zoned:50/5:30/15:20/80\n")
        job.write("randrepeat=0\n")
        # time based vs data based
        #job.write("time_based\n")
        #job.write("runtime=57600\n")
        job.write("size=20TB\n") #20TB
        job.write("norandommap\n")
        job.write("group_reporting=1\n")
        # records the performance of the drive. not needed for an endurance test but here just in case.
        #job.write("log_avg_msec=1000")
        #job.write("per_job_logs=0")
        #job.write("write_lat_log=endurance_lat")
        #job.write("write_bw_log=endurance_bw")
        job.close()
        return job
    endurance = create_job_file()
    #f = open(endurance.name, "r")
    #print(f.read())
    test=subprocess.Popen(["fio", "--output-format=json+", "--output=JEDEC_Enterprise.json", endurance.name], shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    test.wait()
    print("Endurance phase finished. Now closing.")
    return 1

def summary():
    global _drive
    collect_system_info()
    # calculate currently estimated TBW from devices.
    calculatedTBW = calculate_TBW()
    # generate checksum of device for retention test.
    checksum=subprocess.check_output("sudo pv "+_drive+"| md5sum",shell=True)
    # record all errors (read errors, uecc, hw recovered, serial number, temperature, erase count)
    return calculatedTBW

def collect_system_info():
    # want to get model name, capacity, serial number, 
    # also get OS, system info
    
    return 1

def open_smart(file_name):
    written = 1
    life = 1
    f = open(file_name)
    data = json.load(f)
    for smart_attr in data['ata_smart_attributes']['table']:
        if(smart_attr['id'] == 231): # Life left
            life = smart_attr['raw']['value']
        elif(smart_attr['id'] == 241): # GB written
            written = smart_attr['raw']['value']
    return (written, life)

def parse_smart():
    # get the start and the end files
    start_file = "./JEDEC_TEST_FIO/logs/precond/json_SMART.json"
    end_file = "./JEDEC_TEST_FIO/logs/end/json_SMART.json"
    (gb_start, life_start) = open_smart(start_file)
    (gb_end, life_end) = open_smart(end_file)
    return (gb_start,gb_end,life_start,life_end)

def calculate_TBW():
    (GB_start, GB_end, life_start,life_end) = (open_smart())
    TBW = ((GB_end - GB_start)/1000) * 100 / (life_end - life_start)
    return TBW

def main():
    global _drive
    _drive = identify_drive()
    #generate file structure
    if not os.path.isdir("./JEDEC_TEST_FIO"):
        os.mkdir("./JEDEC_TEST_FIO")
    os.chdir("./JEDEC_TEST_FIO")
    if not os.path.isdir("./logs"):
        os.mkdir("./logs")
    collect_system_info()
    record_drive_data("start")
    precondition()
    record_drive_data("precond")
    endurance_phase()
    record_drive_data("end")
    summary()
    return 1

if __name__ == "__main__":
    main()