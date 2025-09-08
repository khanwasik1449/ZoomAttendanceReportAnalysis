import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import io # Import io module for handling string as file

st.set_page_config(layout="wide")

st.title("Zoom Attendance Report Analyzer (Custom Format)")

st.write("Upload your Zoom meeting participant report (CSV format). This version is tailored for reports with meeting metadata at the top and participant details below.")

uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

if uploaded_file is not None:
    try:
        # Read the entire file content as a string
        file_content = uploaded_file.getvalue().decode("utf-8")

        # --- Extract Meeting Metadata ---
        meeting_info_lines = []
        participant_data_started = False
        participant_data_lines = []

        # Find the line where participant data starts
        # Assuming participant data starts after "Name (original name),Email,Total duration (minutes),Guest"
        for line in file_content.splitlines():
            if line.strip().startswith("Name (original name),Email"):
                participant_data_started = True
                participant_data_lines.append(line) # Add the header line
                continue
            
            if not participant_data_started:
                meeting_info_lines.append(line)
            else:
                if line.strip() and not line.strip().startswith("Zoom Report"): # Avoid trailing "Zoom Report" line
                    participant_data_lines.append(line)

        # Parse meeting metadata (first non-empty line before participant data)
        meeting_metadata = {}
        if meeting_info_lines:
            # Find the line with Topic, ID, Host, etc.
            # Assuming it's the first line after the initial blank lines/BOM
            header_line_found = False
            data_line_found = False
            for line in meeting_info_lines:
                line = line.strip().lstrip('\ufeff') # Remove BOM if present
                if line.startswith("Topic,ID,Host"): # This is the header for meeting info
                    header_line_parts = [part.strip() for part in line.split(',')]
                    header_line_found = True
                elif header_line_found and line: # This is the data line for meeting info
                    data_line_parts = [part.strip() for part in line.split(',')]
                    if len(header_line_parts) == len(data_line_parts):
                        meeting_metadata = dict(zip(header_line_parts, data_line_parts))
                        data_line_found = True
                        break # Found the metadata, stop
            
        if not meeting_metadata:
            st.warning("Could not parse meeting metadata (Topic, Start Time, etc.) from the file. Proceeding with participant data only.")
            meeting_start_time_obj = None
            meeting_end_time_obj = None
            meeting_duration_official = None
        else:
            st.subheader("Meeting Overview")
            st.write(f"**Topic:** {meeting_metadata.get('Topic', 'N/A')}")
            st.write(f"**Meeting ID:** {meeting_metadata.get('ID', 'N/A')}")
            st.write(f"**Host:** {meeting_metadata.get('Host', 'N/A')}")
            meeting_duration_official = pd.to_numeric(meeting_metadata.get('Duration (minutes)', 0), errors='coerce')
            st.write(f"**Official Duration:** {meeting_duration_official:.0f} minutes")

            try:
                # Zoom often uses "MM-DD-YYYY HH:MM:SS AM/PM"
                meeting_start_time_str = meeting_metadata.get('Start time')
                meeting_end_time_str = meeting_metadata.get('End time')
                meeting_start_time_obj = datetime.strptime(meeting_start_time_str, "%m-%d-%Y %I:%M:%S %p")
                meeting_end_time_obj = datetime.strptime(meeting_end_time_str, "%m-%d-%Y %I:%M:%S %p")
                st.write(f"**Start Time:** {meeting_start_time_obj.strftime('%Y-%m-%d %H:%M:%S')}")
                st.write(f"**End Time:** {meeting_end_time_obj.strftime('%Y-%m-%d %H:%M:%S')}")
            except ValueError:
                st.warning("Could not parse official start/end times. Please check the format.")
                meeting_start_time_obj = None
                meeting_end_time_obj = None


        # --- Parse Participant Data ---
        # Use io.StringIO to treat the list of lines as a file
        participant_csv_content = "\n".join(participant_data_lines)
        df = pd.read_csv(io.StringIO(participant_csv_content))

        # Rename columns to a consistent format for easier access
        df.rename(columns={
            "Name (original name)": "Name",
            "Email": "User Email",
            "Total duration (minutes)": "Duration (Minutes)"
        }, inplace=True)

        st.subheader("Raw Participant Data Preview")
        st.dataframe(df.head())

        # --- Data Cleaning and Preprocessing ---
        df['Duration (Minutes)'] = pd.to_numeric(df['Duration (Minutes)'], errors='coerce').fillna(0)
        
        st.success("CSV loaded and preprocessed successfully!")

        # --- Analysis Parameters ---
        st.sidebar.header("Analysis Settings")
        
        # If official duration is known, use it, else allow user to input a reference
        reference_duration = meeting_duration_official if meeting_duration_official else df['Duration (Minutes)'].max() # Use max as a fallback
        if reference_duration == 0: reference_duration = 1 # Avoid division by zero
        
        min_attendance_percentage = st.sidebar.slider(
            "Consider 'Full Attended' if duration is at least X% of official/max meeting duration:",
            min_value=0, max_value=100, value=75
        )
        
        # --- Perform Analysis ---
        st.subheader("Attendance Summary")

        total_participants = df['User Email'].nunique() if 'User Email' in df.columns else df['Name'].nunique()
        st.write(f"**Total Unique Participants:** {total_participants}")

        # Calculate attendance status based on duration percentage
        df['Attendance %'] = (df['Duration (Minutes)'] / reference_duration * 100).round(2)
        df['Attendance Status'] = df['Attendance %'].apply(
            lambda x: "Full Attended" if x >= min_attendance_percentage else "Partial Attended"
        )
        df.loc[df['Duration (Minutes)'] == 0, 'Attendance Status'] = "Did Not Attend"
        
        # If email is often blank, filter by unique name
        if 'User Email' in df.columns and df['User Email'].isnull().all():
             st.warning("Email column is empty. Analysis will rely on unique names, which might not be perfectly unique.")
             unique_participants_df = df.drop_duplicates(subset=['Name']).copy()
        else:
             unique_participants_df = df.drop_duplicates(subset=['User Email']).copy()


        st.subheader("Individual Participant Details")
        st.dataframe(unique_participants_df[['Name', 'User Email', 'Duration (Minutes)', 'Attendance %', 'Attendance Status']])

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Attendance Overview")
            
            status_counts = unique_participants_df['Attendance Status'].value_counts()
            
            st.metric("Total Unique Participants", total_participants)
            if "Full Attended" in status_counts:
                st.metric("Full Attended Participants", status_counts["Full Attended"])
            if "Partial Attended" in status_counts:
                st.metric("Partial Attended Participants", status_counts["Partial Attended"])
            if "Did Not Attend" in status_counts:
                st.metric("Did Not Attend Participants (0 min)", status_counts["Did Not Attend"])

            # Pie chart for attendance status
            fig_status = px.pie(unique_participants_df, names='Attendance Status', title='Overall Attendance Status')
            st.plotly_chart(fig_status, use_container_width=True)

        with col2:
            st.subheader("Duration Distribution")
            fig_duration = px.histogram(unique_participants_df, x='Duration (Minutes)',
                                        title='Distribution of Participant Durations',
                                        nbins=20,
                                        labels={'Duration (Minutes)': 'Duration in Minutes'})
            st.plotly_chart(fig_duration, use_container_width=True)
            
            st.write(f"**Average Duration per Unique Participant:** {unique_participants_df['Duration (Minutes)'].mean():.2f} minutes")
            st.write(f"**Median Duration per Unique Participant:** {unique_participants_df['Duration (Minutes)'].median():.2f} minutes")

        st.subheader("Download Detailed Report")
        csv_export = unique_participants_df[['Name', 'User Email', 'Duration (Minutes)', 'Attendance %', 'Attendance Status']].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Analyzed Attendance Report CSV",
            data=csv_export,
            file_name="zoom_attendance_analysis_custom.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(f"An error occurred: {e}. Please ensure your CSV format matches the expected structure.")
        st.write("Common issues: File encoding, unexpected line breaks, or different column names than 'Name (original name)', 'Email', 'Total duration (minutes)'.")

st.sidebar.markdown("---")
st.sidebar.info("Upload your Zoom participant report CSV.")

st.write("Need to analyze another report?")